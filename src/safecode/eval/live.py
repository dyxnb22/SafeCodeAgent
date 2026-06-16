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
import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_SNAPSHOT_DIR = (
    Path(__file__).parent.parent.parent.parent / "tests" / "snapshots" / "live_eval"
)
_LATEST_JSON = _SNAPSHOT_DIR / "latest.json"
_BASELINE_JSON = _SNAPSHOT_DIR / "baseline.json"

_PROVIDER_ALLOWLIST = {
    "anthropic": "api.anthropic.com",
    "openai": "api.openai.com",
    "openai-compatible": "api.openai.com",
    "deepseek": "api.deepseek.com",
}


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


def _calculator_fix_fixture() -> LiveEvalFixture:
    setup = {
        "src/calculator.py": "def add(a: int, b: int) -> int:\n    return a - b\n",
        "tests/test_calc.py": (
            "from calculator import add\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n\n"
        ),
    }

    def success(root: Path) -> bool:
        impl = root / "src" / "calculator.py"
        if not impl.exists():
            return False
        tree = ast.parse(impl.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "add"
                and any(isinstance(child, ast.Add) for child in ast.walk(node))
            ):
                return True
        return False

    return LiveEvalFixture(
        name="calculator-fix",
        setup_files=setup,
        goal="Fix src/calculator.py so add(2, 3) returns 5 and tests/test_calc.py passes.",
        success_condition=success,
        max_turns=6,
    )


def _docs_edit_fixture() -> LiveEvalFixture:
    setup = {
        "README.md": "# Widget Service\n\nRun tests with pytest.\n",
        "docs/usage.md": "## Usage\n\nStart the service with `python -m widget`.\n",
    }

    def success(root: Path) -> bool:
        readme = root / "README.md"
        usage = root / "docs" / "usage.md"
        text = readme.read_text(encoding="utf-8") + "\n" + usage.read_text(encoding="utf-8")
        return "SAFECODE_CONFIG" in text and "configuration" in text.lower()

    return LiveEvalFixture(
        name="docs-edit",
        setup_files=setup,
        goal="Document the SAFECODE_CONFIG environment variable in the project docs.",
        success_condition=success,
        max_turns=6,
    )


def _multi_file_refactor_fixture() -> LiveEvalFixture:
    body = "def load_user(user_id):\n    return {'id': user_id}\n"
    user_a = "from users import load_user\n\ndef render(user_id):\n    return load_user(user_id)['id']\n"
    user_b = "from users import load_user\n\ndef audit(user_id):\n    return {'user': load_user(user_id)}\n"
    setup = {
        "src/users.py": body,
        "src/views.py": user_a,
        "src/audit.py": user_b,
    }

    def success(root: Path) -> bool:
        files = [root / "src" / name for name in ("users.py", "views.py", "audit.py")]
        texts = [p.read_text(encoding="utf-8") for p in files]
        return all("fetch_user" in text for text in texts) and not any("load_user" in text for text in texts)

    return LiveEvalFixture(
        name="multi-file-refactor",
        setup_files=setup,
        goal=(
            "Rename load_user to fetch_user everywhere, including imports and all call sites "
            "in src/users.py, src/views.py, and src/audit.py."
        ),
        success_condition=success,
        max_turns=8,
    )


def _test_failure_repair_fixture() -> LiveEvalFixture:
    setup = {
        "src/strings.py": "def title_case(value: str) -> str:\n    return value.upper()\n",
        "tests/test_strings.py": (
            "from strings import title_case\n\n"
            "def test_title_case_words():\n"
            "    assert title_case('hello world') == 'Hello World'\n"
        ),
    }

    def success(root: Path) -> bool:
        impl = root / "src" / "strings.py"
        text = impl.read_text(encoding="utf-8")
        return ".title()" in text or "capitalize" in text

    return LiveEvalFixture(
        name="test-failure-repair",
        setup_files=setup,
        goal=(
            "tests/test_strings.py has a clear assertion failure. "
            "Fix title_case() in src/strings.py so the test passes."
        ),
        success_condition=success,
        max_turns=6,
    )


def _config_schema_migration_fixture() -> LiveEvalFixture:
    setup = {
        "src/settings.py": (
            "DEFAULT_CONFIG = {'retries': 3, 'timeout': 10}\n\n"
            "def load_config(overrides=None):\n"
            "    data = dict(DEFAULT_CONFIG)\n"
            "    if overrides:\n"
            "        data.update(overrides)\n"
            "    return data\n\n"
            "def timeout_seconds(config):\n"
            "    return config['timeout']\n"
        ),
        "tests/test_settings.py": (
            "from settings import load_config, timeout_seconds\n\n"
            "def test_load_config_mapping_compatibility():\n"
            "    cfg = load_config({'timeout': 5})\n"
            "    assert cfg['timeout'] == 5\n"
            "    assert timeout_seconds(cfg) == 5\n"
        ),
    }

    def success(root: Path) -> bool:
        impl = root / "src" / "settings.py"
        text = impl.read_text(encoding="utf-8")
        if "dataclass" not in text or "class" not in text:
            return False
        tree = ast.parse(text)
        has_config_class = any(isinstance(node, ast.ClassDef) and "Config" in node.name for node in ast.walk(tree))
        keeps_mapping_compat = "__getitem__" in text or "Mapping" in text or "asdict" in text
        return has_config_class and keeps_mapping_compat

    return LiveEvalFixture(
        name="config-schema-migration",
        setup_files=setup,
        goal=(
            "Migrate the dict-based config in src/settings.py to a dataclass while keeping "
            "existing callers compatible with cfg['timeout'] and timeout_seconds(cfg)."
        ),
        success_condition=success,
        max_turns=8,
    )


def default_live_fixtures() -> list[LiveEvalFixture]:
    return [
        _calculator_fix_fixture(),
        _docs_edit_fixture(),
        _multi_file_refactor_fixture(),
        _test_failure_repair_fixture(),
        _config_schema_migration_fixture(),
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

            cfg = SafeCodeConfig.load(root)
            cfg.llm.provider = self.provider
            if self.model:
                cfg.llm.model = self.model
            cfg.sandbox.network_enabled = True
            host = _PROVIDER_ALLOWLIST.get(self.provider)
            if host:
                cfg.sandbox.network_allowlist = [host]

            llm = create_llm_client(cfg)

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
            edit_result = orch.edit(fixture.goal)
            orch.apply(edit_result.proposal)
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
