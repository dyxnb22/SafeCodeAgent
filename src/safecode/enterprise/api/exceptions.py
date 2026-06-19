"""Team Server API exceptions."""


class TeamServerDependencyError(Exception):
    """Raised when the team-server optional extra is required but missing."""


class SettingsValidationError(Exception):
    """Raised when Team Server settings fail validation."""
