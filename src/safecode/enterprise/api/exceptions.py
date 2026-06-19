"""Team Server API exceptions."""


class TeamServerDependencyError(Exception):
    """Raised when the team-server optional extra is required but missing."""


class SettingsValidationError(Exception):
    """Raised when Team Server settings fail validation."""


class TenantScopeDeniedError(Exception):
    """Raised when the authenticated subject cannot access the requested tenant."""
