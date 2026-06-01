"""Release smoke-test: validates the most important local release surfaces quickly."""

from __future__ import annotations

from dataclasses import dataclass, field


EXPECTED_POLICY_NAMES: frozenset[str] = frozenset(
    {"strict", "balanced", "experimental", "normal", "learning"}
)


@dataclass(frozen=True)
class SmokeTestCase:
    """One smoke-test result."""

    name: str
    passed: bool
    detail: str


@dataclass
class SmokeTestResult:
    """Aggregated smoke-test results."""

    cases: list[SmokeTestCase] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.cases)

    @property
    def failed(self) -> list[SmokeTestCase]:
        return [c for c in self.cases if not c.passed]


def _check_import_version() -> SmokeTestCase:
    try:
        import safecode
        v = safecode.__version__
        if not isinstance(v, str) or not v:
            return SmokeTestCase("import_version", False, f"__version__ is not a non-empty string: {v!r}")
        return SmokeTestCase("import_version", True, f"safecode.__version__ = {v!r}")
    except Exception as exc:  # noqa: BLE001
        return SmokeTestCase("import_version", False, f"import failed: {exc}")


def _check_cli_version() -> SmokeTestCase:
    try:
        from typer.testing import CliRunner
        from safecode.cli import app
        result = CliRunner().invoke(app, ["version"])
        if result.exit_code != 0:
            return SmokeTestCase("cli_version", False, f"exit_code={result.exit_code}: {result.output.strip()}")
        import safecode
        if safecode.__version__ not in result.output:
            return SmokeTestCase(
                "cli_version", False,
                f"__version__ {safecode.__version__!r} not in CLI output: {result.output.strip()!r}"
            )
        return SmokeTestCase("cli_version", True, f"sac version → exit 0, version present")
    except Exception as exc:  # noqa: BLE001
        return SmokeTestCase("cli_version", False, f"CLI invocation failed: {exc}")


def _check_version_consistency() -> SmokeTestCase:
    try:
        from safecode.release.version_guard import check_version_consistency
        result = check_version_consistency()
        if result.ok:
            return SmokeTestCase("version_consistency", True, result.message)
        return SmokeTestCase("version_consistency", False, result.message)
    except Exception as exc:  # noqa: BLE001
        return SmokeTestCase("version_consistency", False, f"check raised: {exc}")


def _check_docs_finalized() -> SmokeTestCase:
    try:
        import safecode
        from safecode.release.docs_guard import check_docs_finalized
        result = check_docs_finalized(safecode.__version__)
        if result.ok:
            return SmokeTestCase("docs_finalized", True, f"docs finalized for v{safecode.__version__}")
        summary = "; ".join(result.issues)
        return SmokeTestCase("docs_finalized", False, summary)
    except Exception as exc:  # noqa: BLE001
        return SmokeTestCase("docs_finalized", False, f"check raised: {exc}")


def _check_policy_names() -> SmokeTestCase:
    try:
        from safecode.config import KNOWN_POLICY_NAMES
        missing = EXPECTED_POLICY_NAMES - KNOWN_POLICY_NAMES
        if missing:
            return SmokeTestCase(
                "policy_names", False,
                f"KNOWN_POLICY_NAMES is missing: {sorted(missing)}"
            )
        return SmokeTestCase(
            "policy_names", True,
            f"all expected policy names present: {sorted(EXPECTED_POLICY_NAMES)}"
        )
    except Exception as exc:  # noqa: BLE001
        return SmokeTestCase("policy_names", False, f"import failed: {exc}")


def run_smoke_tests() -> SmokeTestResult:
    """Run all release smoke tests and return the aggregated result."""
    result = SmokeTestResult()
    result.cases.append(_check_import_version())
    result.cases.append(_check_cli_version())
    result.cases.append(_check_version_consistency())
    result.cases.append(_check_policy_names())
    result.cases.append(_check_docs_finalized())
    return result


def render_smoke_results(result: SmokeTestResult) -> str:
    """Render smoke-test results as human-readable text."""
    lines: list[str] = ["SafeCode Release Smoke Test", "=========================="]
    for case in result.cases:
        status = "PASS" if case.passed else "FAIL"
        lines.append(f"  [{status}] {case.name}: {case.detail}")
    lines.append("")
    if result.ok:
        lines.append("All smoke tests passed.")
    else:
        failed_names = ", ".join(c.name for c in result.failed)
        lines.append(f"FAILED: {failed_names}")
    return "\n".join(lines)
