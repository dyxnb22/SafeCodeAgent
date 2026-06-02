"""Release smoke-test: validates the most important local release surfaces quickly."""

from __future__ import annotations

from dataclasses import dataclass, field

from safecode.core.diagnostic import Diagnostic
from safecode.release.ux import header, next_steps


EXPECTED_POLICY_NAMES: frozenset[str] = frozenset(
    {"strict", "balanced", "experimental", "normal", "learning"}
)


@dataclass(frozen=True)
class SmokeTestCase:
    """One smoke-test result (legacy-shape view)."""

    name: str
    passed: bool
    detail: str

    def to_diagnostic(self) -> Diagnostic:
        """Return the typed Diagnostic for this smoke case."""
        return Diagnostic.from_bool(self.name, self.passed, self.detail)


def _from_diagnostic(diagnostic: Diagnostic) -> SmokeTestCase:
    """Render a Diagnostic in the legacy SmokeTestCase shape."""
    return SmokeTestCase(
        name=diagnostic.name,
        passed=diagnostic.passed,
        detail=diagnostic.message,
    )


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

    def to_diagnostics(self) -> list[Diagnostic]:
        """Return typed diagnostics for each smoke case."""
        return [case.to_diagnostic() for case in self.cases]


def _diag_import_version() -> Diagnostic:
    try:
        import safecode
        v = safecode.__version__
        if not isinstance(v, str) or not v:
            return Diagnostic.from_bool(
                "import_version", False, f"__version__ is not a non-empty string: {v!r}"
            )
        return Diagnostic.from_bool(
            "import_version", True, f"safecode.__version__ = {v!r}"
        )
    except Exception as exc:  # noqa: BLE001
        return Diagnostic.from_bool("import_version", False, f"import failed: {exc}")


def _diag_cli_version() -> Diagnostic:
    try:
        from typer.testing import CliRunner
        from safecode.cli import app
        result = CliRunner().invoke(app, ["version"])
        if result.exit_code != 0:
            return Diagnostic.from_bool(
                "cli_version", False,
                f"exit_code={result.exit_code}: {result.output.strip()}",
            )
        import safecode
        if safecode.__version__ not in result.output:
            return Diagnostic.from_bool(
                "cli_version", False,
                f"__version__ {safecode.__version__!r} not in CLI output: {result.output.strip()!r}",
            )
        return Diagnostic.from_bool(
            "cli_version", True, "sac version → exit 0, version present"
        )
    except Exception as exc:  # noqa: BLE001
        return Diagnostic.from_bool("cli_version", False, f"CLI invocation failed: {exc}")


def _diag_version_consistency() -> Diagnostic:
    try:
        from safecode.release.version_guard import check_version_consistency
        result = check_version_consistency()
        return Diagnostic.from_bool("version_consistency", result.ok, result.message)
    except Exception as exc:  # noqa: BLE001
        return Diagnostic.from_bool(
            "version_consistency", False, f"check raised: {exc}"
        )


def _diag_docs_finalized() -> Diagnostic:
    try:
        import safecode
        from safecode.release.docs_guard import check_docs_finalized
        result = check_docs_finalized(safecode.__version__)
        if result.ok:
            return Diagnostic.from_bool(
                "docs_finalized", True, f"docs finalized for v{safecode.__version__}"
            )
        return Diagnostic.from_bool("docs_finalized", False, "; ".join(result.issues))
    except Exception as exc:  # noqa: BLE001
        return Diagnostic.from_bool("docs_finalized", False, f"check raised: {exc}")


def _diag_policy_names() -> Diagnostic:
    try:
        from safecode.config import KNOWN_POLICY_NAMES
        missing = EXPECTED_POLICY_NAMES - KNOWN_POLICY_NAMES
        if missing:
            return Diagnostic.from_bool(
                "policy_names", False,
                f"KNOWN_POLICY_NAMES is missing: {sorted(missing)}",
            )
        return Diagnostic.from_bool(
            "policy_names", True,
            f"all expected policy names present: {sorted(EXPECTED_POLICY_NAMES)}",
        )
    except Exception as exc:  # noqa: BLE001
        return Diagnostic.from_bool("policy_names", False, f"import failed: {exc}")


# Backward-compatible wrappers — preserved so any external import of the
# `_check_*` helpers continues to function. Internally we route through the
# Diagnostic substrate.
def _check_import_version() -> SmokeTestCase:
    return _from_diagnostic(_diag_import_version())


def _check_cli_version() -> SmokeTestCase:
    return _from_diagnostic(_diag_cli_version())


def _check_version_consistency() -> SmokeTestCase:
    return _from_diagnostic(_diag_version_consistency())


def _check_docs_finalized() -> SmokeTestCase:
    return _from_diagnostic(_diag_docs_finalized())


def _check_policy_names() -> SmokeTestCase:
    return _from_diagnostic(_diag_policy_names())


def collect_smoke_diagnostics() -> list[Diagnostic]:
    """Return typed diagnostics for each smoke case (v2.8.x substrate)."""
    return [
        _diag_import_version(),
        _diag_cli_version(),
        _diag_version_consistency(),
        _diag_policy_names(),
        _diag_docs_finalized(),
    ]


def run_smoke_tests() -> SmokeTestResult:
    """Run all release smoke tests and return the aggregated result."""
    result = SmokeTestResult()
    for diag in collect_smoke_diagnostics():
        result.cases.append(_from_diagnostic(diag))
    return result


def render_smoke_results(result: SmokeTestResult) -> str:
    """Render smoke-test results as human-readable text."""
    lines: list[str] = header("SafeCode Release Smoke Test", result.ok)
    for case in result.cases:
        status = "PASS" if case.passed else "FAIL"
        lines.append(f"  [{status}] {case.name}: {case.detail}")
    lines.append("")
    if result.ok:
        lines.append("All smoke tests passed.")
        lines.extend(next_steps([], ok_message="No smoke-test follow-up needed."))
    else:
        failed_names = ", ".join(c.name for c in result.failed)
        lines.append(f"FAILED: {failed_names}")
        lines.extend(next_steps(["Fix failing smoke checks, then rerun sac release smoke."]))
    return "\n".join(lines)
