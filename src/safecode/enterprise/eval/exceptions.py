"""Enterprise evaluation exceptions."""


class EvalError(Exception):
    """Base enterprise evaluation error."""


class DuplicateCaseIdError(EvalError):
    """Raised when two cases share the same case_id."""


class InvalidEvalCaseError(EvalError):
    """Raised when a case file fails validation."""
