"""Core typed substrates shared across SafeCode subsystems."""

from safecode.core.diagnostic import (
    Diagnostic,
    DiagnosticGroup,
    DiagnosticStatus,
    aggregate_status,
    all_passed,
)

__all__ = [
    "Diagnostic",
    "DiagnosticGroup",
    "DiagnosticStatus",
    "aggregate_status",
    "all_passed",
]
