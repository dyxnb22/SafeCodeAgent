"""Team Server API package (v2.1).

中文说明
--------
企业 Team Server 的 HTTP API 层，基于 FastAPI 暴露 runs、traces、approvals、
evidence、eval、webhooks 等路由。``server.build_application`` 为 Uvicorn 工厂入口；
``app.create_app`` 负责组装依赖（持久化后端、OIDC 校验器、租户限流）并注册
全局异常处理器。本地模式与 SERVER 模式通过 ``TeamServerSettings.runtime_mode`` 区分
认证策略。
"""

from safecode.enterprise.api.exceptions import (
    SettingsValidationError,
    TeamServerDependencyError,
)
from safecode.enterprise.api.settings import (
    DOCUMENTED_ENV_VARS,
    RuntimeMode,
    TeamServerSettings,
    load_team_server_settings,
    load_team_server_settings_from_env,
)

__all__ = [
    "DOCUMENTED_ENV_VARS",
    "RuntimeMode",
    "SettingsValidationError",
    "TeamServerDependencyError",
    "TeamServerSettings",
    "load_team_server_settings",
    "load_team_server_settings_from_env",
]
