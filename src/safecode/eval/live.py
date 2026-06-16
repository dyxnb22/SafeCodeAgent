"""Live eval harness for v5.6.1.

Runs real coding tasks against a live LLM provider and collects quality
metrics (success, turns, tool calls, redundant reads, tokens, wall time).

Usage:
    SAFECODE_LIVE_TESTS=1 sac eval --mode live --provider anthropic

Without SAFECODE_LIVE_TESTS=1 the command prints a skip notice and exits 0.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_SNAPSHOT_DIR = (
    Path(__file__).parent.parent.parent.parent / "tests" / "snapshots" / "live_eval"
)
_LATEST_JSON = _SNAPSHOT_DIR / "latest.json"
_BASELINE_JSON = _SNAPSHOT_DIR / "baseline.json"


# ---------------------------------------------------------------------------
# Fixture format
# ---------------------------------------------------------------------------


@dataclass
class LiveEvalFixture:
    """One live eval task.

    ``setup_files``: dict of ``{relative_path: content}`` written into a temp project.
    ``goal``: natural-language task given to the agent.
    ``success_condition``: callable ``(project_root: Path) -> bool``.
    ``max_turns``: hard cap on agent loop iterations.
    """

    name: str
    setup_files: dict[str, str]
    goal: str
    success_condition: Callable[[Path], bool]
    max_turns: int = 8


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class LiveEvalResult:
    """Metrics collected for one live fixture run."""

    fixture_name: str
    success: bool
    turns_used: int
    tool_calls: int
    redundant_reads: int
    input_tokens: int
    output_tokens: int
    wall_seconds: float
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_name": self.fixture_name,
            "success": self.success,
            "turns_used": self.turns_used,
            "tool_calls": self.tool_calls,
            "redundant_reads": self.redundant_reads,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "wall_seconds": round(self.wall_seconds, 3),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Default fixtures
# ---------------------------------------------------------------------------


def _python_add_function_fixture() -> LiveEvalFixture:
    setup = {
        "src/calc.py": "def add(a: int, b: int) -> int:\n    return a + b\n",
        "tests/test_calc.py": (
            "from calc import add, multiply\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n\n"
            "def test_multiply():\n    assert multiply(3, 4) == 12\n"
        ),
    }

    def success(root: Path) -> bool:
        impl = root / "src" / "calc.py"
        return impl.exists() and "multiply" in impl.read_text()

    return LiveEvalFixture(
        name="python-add-function",
        setup_files=setup,
        goal="Add a multiply(a, b) function to src/calc.py so tests/test_calc.py passes.",
        success_condition=success,
        max_turns=6,
    )


def _python_fix_failing_test_fixture() -> LiveEvalFixture:
    setup = {
        "src/greet.py": "def greet(name: str) -> str:\n    return f'Hello {name}'\n",
        "tests/test_greet.py": (
            "from greet import greet\n\n"
            "def test_greet():\n    assert greet('Alice') == 'Hello, Alice!'\n"
        ),
    }

    def success(root: Path) -> bool:
        impl = root / "src" / "greet.py"
        return impl.exists() and "Hello," in impl.read_text()

    return LiveEvalFixture(
        name="python-fix-failing-test",
        setup_files=setup,
        goal=(
            "The test in tests/test_greet.py is failing. "
            "Fix greet() in src/greet.py so the test passes."
        ),
        success_condition=success,
        max_turns=6,
    )


def _python_refactor_rename_fixture() -> LiveEvalFixture:
    body = "def compute_total(items):\n    return sum(items)\n"
    user_a = "from calc import compute_total\n\ndef report():\n    return compute_total([1,2,3])\n"
    user_b = "from calc import compute_total\n\nresult = compute_total(range(5))\n"
    setup = {
        "src/calc.py": body,
        "src/report.py": user_a,
        "src/batch.py": user_b,
    }

    def success(root: Path) -> bool:
        calc = (root / "src" / "calc.py").read_text()
        report = (root / "src" / "report.py").read_text()
        batch = (root / "src" / "batch.py").read_text()
        return "sum_items" in calc and "sum_items" in report and "sum_items" in batch

    return LiveEvalFixture(
        name="python-refactor-rename",
        setup_files=setup,
        goal=(
            "Rename compute_total to sum_items everywhere: "
            "src/calc.py, src/report.py, and src/batch.py."
        ),
        success_condition=success,
        max_turns=8,
    )


def _go_add_handler_fixture() -> LiveEvalFixture:
    main_go = (
        'package main\n\nimport (\n\t"fmt"\n\t"net/http"\n)\n\n'
        'func healthHandler(w http.ResponseWriter, r *http.Request) {\n'
        '\tfmt.Fprintln(w, "ok")\n}\n\n'
        'func main() {\n'
        '\thttp.HandleFunc("/health", healthHandler)\n'
        '\thttp.ListenAndServe(":8080", nil)\n}\n'
    )
    setup = {"main.go": main_go}

    def success(root: Path) -> bool:
        text = (root / "main.go").read_text()
        return "/ping" in text or "pingHandler" in text

    return LiveEvalFixture(
        name="go-add-handler",
        setup_files=setup,
        goal='Add a GET /ping handler to main.go that writes "pong" to the response.',
        success_condition=success,
        max_turns=6,
    )


def _ts_fix_type_error_fixture() -> LiveEvalFixture:
    ts_src = (
        "interface User {\n  name: string;\n  age: number;\n}\n\n"
        "function greetUser(user: User): string {\n"
        "  return `Hello ${user.name}, you are ${user.years} years old`;\n"
        "}\n"
    )
    setup = {"src/user.ts": ts_src}

    def success(root: Path) -> bool:
        text = (root / "src" / "user.ts").read_text()
        return "user.age" in text and "user.years" not in text

    return LiveEvalFixture(
        name="ts-fix-type-error",
        setup_files=setup,
        goal=(
            "Fix the TypeScript type error in src/user.ts: "
            "the User interface has 'age' but greetUser accesses 'user.years'."
        ),
        success_condition=success,
        max_turns=5,
    )


def default_live_fixtures() -> list[LiveEvalFixture]:
    return [
        _python_add_function_fixture(),
        _python_fix_failing_test_fixture(),
        _python_refactor_rename_fixture(),
        _go_add_handler_fixture(),
        _ts_fix_type_error_fixture(),
    ]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class LiveEvalRunner:
    """Runs live eval fixtures against a real LLM provider.

    Import the agent orchestrator only inside ``run_fixture`` to avoid circular
    imports when the module is imported in tests.
    """

    def __init__(self, provider: str = "anthropic", model: str | None = None) -> None:
        self.provider = provider
        self.model = model

    def run_fixture(self, fixture: LiveEvalFixture) -> LiveEvalResult:
        tmp = tempfile.mkdtemp(prefix="sac_live_eval_")
        try:
            return self._run_in_tmp(fixture, Path(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _run_in_tmp(self, fixture: LiveEvalFixture, root: Path) -> LiveEvalResult:
        for rel, content in fixture.setup_files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        t0 = time.perf_counter()
        turns = 0
        tool_calls = 0
        redundant_reads = 0
        input_tokens = 0
        output_tokens = 0
        error: str | None = None

        try:
            from safecode.agent.orchestrator import AgentOrchestrator
            from safecode.config import SafeCodeConfig
            from safecode.llm.factory import create_llm_client

            cfg = SafeCodeConfig.load()
            cfg.llm.provider = self.provider
            if self.model:
                cfg.llm.model = self.model

            llm = create_llm_client(cfg.llm)

            read_paths: list[str] = []

            def on_step(step_info: dict[str, Any]) -> None:
                nonlocal turns, tool_calls, redundant_reads, input_tokens, output_tokens
                turns += 1
                tool_calls += step_info.get("tool_calls", 0)
                input_tokens += step_info.get("input_tokens", 0)
                output_tokens += step_info.get("output_tokens", 0)
                path = step_info.get("tool_target", "")
                if path and step_info.get("tool_intent") == "read_file":
                    if path in read_paths:
                        redundant_reads += 1
                    else:
                        read_paths.append(path)

            orch = AgentOrchestrator(
                project_root=root,
                config=cfg,
                llm_client=llm,
                on_step=on_step,
            )
            orch.edit(fixture.goal)
            success = fixture.success_condition(root)
        except Exception as exc:
            success = False
            error = f"{type(exc).__name__}: {exc}"

        wall = max(time.perf_counter() - t0, 0.0)
        return LiveEvalResult(
            fixture_name=fixture.name,
            success=success,
            turns_used=turns,
            tool_calls=tool_calls,
            redundant_reads=redundant_reads,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            wall_seconds=wall,
            error=error,
        )

    def run_all(
        self, fixtures: list[LiveEvalFixture] | None = None
    ) -> list[LiveEvalResult]:
        if fixtures is None:
            fixtures = default_live_fixtures()
        return [self.run_fixture(f) for f in fixtures]


# ---------------------------------------------------------------------------
# Snapshot I/O and ratchet
# ---------------------------------------------------------------------------


def save_latest(results: list[LiveEvalResult], path: Path = _LATEST_JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "results": [r.as_dict() for r in results],
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def load_results_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("results", [])


def check_ratchet(
    results: list[LiveEvalResult],
    baseline_path: Path = _BASELINE_JSON,
) -> list[str]:
    """Return a list of ratchet failures.

    A ratchet failure occurs when a fixture that previously succeeded now fails.
    """
    baseline_results = {r["fixture_name"]: r for r in load_results_json(baseline_path)}
    failures: list[str] = []
    for result in results:
        prev = baseline_results.get(result.fixture_name)
        if prev and prev.get("success") and not result.success:
            failures.append(
                f"{result.fixture_name}: was passing in baseline, now failing"
                + (f" — {result.error}" if result.error else "")
            )
    return failures


def render_live_summary(results: list[LiveEvalResult]) -> str:
    lines = ["SafeCode Live Eval Results", "=" * 40]
    passed = sum(1 for r in results if r.success)
    lines.append(f"Passed: {passed}/{len(results)}")
    lines.append("")
    for r in results:
        status = "PASS" if r.success else "FAIL"
        lines.append(
            f"[{status}] {r.fixture_name}  "
            f"turns={r.turns_used}  "
            f"tools={r.tool_calls}  "
            f"redundant_reads={r.redundant_reads}  "
            f"tokens={r.input_tokens+r.output_tokens}  "
            f"time={r.wall_seconds:.1f}s"
        )
        if r.error:
            lines.append(f"       error: {r.error}")
    return "\n".join(lines)
