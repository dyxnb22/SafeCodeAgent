"""Tenant-scoped API rate limiting (v2.5.3).

中文模块说明：按已认证租户限流（RPM + 并发 run 上限），修复 caller 控桶问题（GA-H4）。
- 架构位置：``app.py`` 中间件；在 tenant 解析之后执行。
- 安全不变量：``/healthz`` 不限流；bucket 键为服务端 canonical tenant_id。
- 学习路径：读 ``test_rate_limits.py``。
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock

from safecode.enterprise.api.read_service import list_runs
from safecode.enterprise.api.settings import TeamServerSettings
from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.worker.status import is_terminal
from safecode.enterprise.workflow.types import WorkflowStatus


class RateLimitExceeded(Exception):
    """Raised when a tenant exceeds configured API limits."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class InflightLimitExceeded(RateLimitExceeded):
    """Raised when a tenant exceeds the concurrent run budget."""


@dataclass
class TenantRateLimiter:
    """In-memory token bucket and inflight counters for /v2 routes."""

    rate_limit_rpm: int
    max_inflight_runs: int
    _windows: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _lock: Lock = field(default_factory=Lock)

    @classmethod
    def from_settings(cls, settings: TeamServerSettings) -> TenantRateLimiter:
        return cls(
            rate_limit_rpm=settings.rate_limit_rpm,
            max_inflight_runs=settings.max_inflight_runs,
        )

    def check_request(self, tenant_id: str) -> None:
        tenant = validate_tenant_id(tenant_id)
        now = time.monotonic()
        window_seconds = 60.0
        with self._lock:
            bucket = self._windows[tenant]
            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()
            if len(bucket) >= self.rate_limit_rpm:
                raise RateLimitExceeded(
                    f"tenant {tenant!r} exceeded rate limit of {self.rate_limit_rpm} requests per minute"
                )
            bucket.append(now)

    def check_inflight(self, backend: object, tenant_id: str) -> None:
        tenant = validate_tenant_id(tenant_id)
        inflight = count_inflight_runs(backend, tenant_id=tenant)
        if inflight >= self.max_inflight_runs:
            raise InflightLimitExceeded(
                f"tenant {tenant!r} exceeded max inflight runs ({self.max_inflight_runs})"
            )


def count_inflight_runs(backend: object, *, tenant_id: str) -> int:
    items, _cursor = list_runs(backend, tenant_id=tenant_id, limit=200)
    count = 0
    for item in items:
        try:
            status = WorkflowStatus(item.status)
        except ValueError:
            continue
        if not is_terminal(status):
            count += 1
    return count
