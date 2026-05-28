"""Network containment checks."""

from urllib.parse import urlparse

from safecode.config import SafeCodeConfig


class NetworkPolicy:
    """Check whether a URL is allowed."""

    def __init__(self, config: SafeCodeConfig | None = None) -> None:
        self.config = config or SafeCodeConfig()

    def assert_allowed(self, url: str) -> None:
        """Raise PermissionError when network access is not allowed."""
        host = urlparse(url).hostname or ""
        if not self.config.sandbox.network_enabled:
            raise PermissionError("Network access is disabled by policy.")
        if self.config.sandbox.network_allowlist and host not in self.config.sandbox.network_allowlist:
            raise PermissionError(f"Host is not allowlisted: {host}")
