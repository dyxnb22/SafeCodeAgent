"""Team Server API exceptions.

中文模块说明：API 层领域异常，由 ``app.py`` 映射为 RFC 7807 problem+json。
- 架构位置：Service 平面错误契约；避免泄漏内部堆栈。
- 安全不变量：403/404 区分授权与存在性；不弱化为 200。
"""


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
