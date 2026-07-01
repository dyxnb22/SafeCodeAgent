"""Cross-process lock coordinating run checkpoint artifacts and PostgreSQL GC.

中文模块说明：按 run 维度的跨进程文件锁，协调 checkpoint 保存、GC 与 purge。
- 架构位置：Data 平面并发控制（R8）；local 与 PG backend 共用。
- 安全不变量：symlink-safe；fork 子进程不继承错误锁所有权。
- 学习路径：读 R8 maintenance 记录与 concurrency 测试。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.workflow.ids import validate_run_id
from safecode.utils.file_lock import keyed_exclusive_lock


def run_artifact_lock_path(
    artifacts_root: Path,
    *,
    tenant_id: str,
    run_id: str,
) -> Path:
    """Return a stable lock path outside the run directory GC may remove."""
    tenant = validate_tenant_id(tenant_id)
    rid = validate_run_id(run_id)
    # Artifact paths are keyed only by run_id, so lock identity must be too.
    # Keeping tenant out of the path prevents two tenant claims for the same
    # run_id from taking different locks over one shared directory.
    return artifacts_root / "enterprise" / "locks" / "run_artifacts" / f"{rid}.lock"


@contextmanager
def run_artifact_lock(
    artifacts_root: Path,
    *,
    tenant_id: str,
    run_id: str,
) -> Iterator[None]:
    """Serialize artifact writes and GC deletes for one run directory."""
    tenant = validate_tenant_id(tenant_id)
    rid = validate_run_id(run_id)
    lock_path = run_artifact_lock_path(
        artifacts_root,
        tenant_id=tenant,
        run_id=rid,
    )
    with keyed_exclusive_lock(f"run-artifact:{tenant}:{rid}", lock_path):
        yield
