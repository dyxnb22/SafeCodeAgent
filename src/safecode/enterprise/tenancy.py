"""Tenant identifier validation shared by all Enterprise layers.

中文模块说明：全 Enterprise 层共用的 tenant_id 校验与规范化（修复路径逃逸类风险）。
- 架构位置：Identity/Data 横切；API、worker、persistence、memory 入口均调用。
- 安全不变量：拒绝 ``.``、``..`` 与非法字符；长度 1–128；用于 SQL 与本地路径键。
- 学习路径：grep ``validate_tenant_id`` 看调用链；读 ``test_memory_governance_offline.py``。
"""

from __future__ import annotations

import re


class MissingTenantIdError(ValueError):
    """Raised when an Enterprise operation lacks a safe tenant identifier."""

_TENANT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_tenant_id(tenant_id: str | None) -> str:
    """Return a canonical tenant identifier safe for SQL and local paths."""
    if tenant_id is None:
        raise MissingTenantIdError("tenant_id is required")
    normalized = tenant_id.strip()
    if not normalized:
        raise MissingTenantIdError("tenant_id is required")
    if normalized in {".", ".."} or not _TENANT_ID_RE.fullmatch(normalized):
        raise MissingTenantIdError(
            "tenant_id must be 1-128 path-safe ASCII characters and start with an alphanumeric"
        )
    return normalized
