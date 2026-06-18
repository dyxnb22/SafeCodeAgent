"""Typed workflow exceptions."""


class WorkflowError(Exception):
    """Base workflow error."""


class UnknownTaskTypeError(WorkflowError):
    """Raised when a workflow receives an unsupported task type."""


class InvalidStateSchemaVersionError(WorkflowError):
    """Raised when persisted state schema is incompatible."""


class InvalidStateUpdateError(WorkflowError):
    """Raised when a node patch attempts to update unknown state keys."""


class InvalidRunIdError(WorkflowError):
    """Raised when run_id fails validation."""


class CheckpointCorruptedError(WorkflowError):
    """Raised when checkpoint JSON is malformed or incomplete."""


class WorkflowInterrupted(WorkflowError):
    """Raised when a workflow pauses for human approval."""


class LangGraphUnavailableError(WorkflowError):
    """Raised when langgraph runtime is selected but dependency is missing."""


class InvalidWorkflowRuntimeError(WorkflowError):
    """Raised for unsupported WORKFLOW_RUNTIME values."""


class ApprovalRequestExistsError(WorkflowError):
    """Raised when an approval request id already exists."""


class RequestAlreadyConsumedError(WorkflowError):
    """Raised when approving or rejecting a consumed request."""


class ApprovalRequestNotFoundError(WorkflowError):
    """Raised when an approval request cannot be found."""


class ApprovalRequestTamperedError(WorkflowError):
    """Raised when request content no longer matches the stored snapshot."""
