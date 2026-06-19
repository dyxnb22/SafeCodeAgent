"""Team Server API exceptions."""


class TeamServerDependencyError(Exception):
    """Raised when the team-server optional extra is required but missing."""


class SettingsValidationError(Exception):
    """Raised when Team Server settings fail validation."""


class TenantScopeDeniedError(Exception):
    """Raised when the authenticated subject cannot access the requested tenant."""


class IdempotencyKeyRequiredError(Exception):
    """Raised when a command endpoint lacks a valid Idempotency-Key header."""


class ApprovalForbiddenError(Exception):
    """Raised when the subject cannot decide an approval request."""


class ApprovalRequestNotFoundError(Exception):
    """Raised when an approval request is missing within tenant scope."""
