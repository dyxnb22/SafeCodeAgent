"""Tenant-scoped read queries for the Team Server API (v2.1.4-T2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from safecode.enterprise.approvals.store import ApprovalRequest, list_requests
from safecode.enterprise.eval.ratchet import baseline_path_for_suite
from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject
from safecode.enterprise.trace.events import TraceEvent
from safecode.enterprise.trace.redaction import DEFAULT_TRACE_EXPORT_PROFILE, apply_profile_to_payload
from safecode.enterprise.trace.timeline import RunTimeline, build_timeline
from safecode.enterprise.workflow.checkpoint import RunCheckpoint, load_checkpoint, runs_root
from safecode.enterprise.workflow.ids import validate_run_id
from safecode.enterprise.workflow.state import EnterpriseRunState

PersistenceBackend = Any


def _is_postgres_backend(backend: object) -> bool:
    try:
        from safecode.enterprise.persistence.postgres.backend import PostgresBackend
    except ImportError:
        return False
    return isinstance(backend, PostgresBackend)


@dataclass(frozen=True)
class RunSummaryView:
    run_id: str
    tenant_id: str
    task_type: str
    status: str
    created_at: str
    updated_at: str


def artifacts_root(backend: PersistenceBackend) -> Path:
    sac_root = getattr(backend, "sac_root", None)
    if sac_root is not None:
        return sac_root
    return backend.artifacts_root


def enforce_tenant_scope(subject: RBACSubject, tenant_id: str) -> str:
    tenant = validate_tenant_id(tenant_id)
    if validate_tenant_id(subject.tenant_id) != tenant:
        from safecode.enterprise.api.exceptions import TenantScopeDeniedError

        raise TenantScopeDeniedError(
            f"subject tenant {subject.tenant_id!r} cannot access tenant {tenant!r}"
        )
    return tenant


def _checkpoint_to_summary(checkpoint: RunCheckpoint) -> RunSummaryView:
    state = checkpoint.state
    return RunSummaryView(
        run_id=state.run_id,
        tenant_id=state.tenant_id,
        task_type=state.task_type.value,
        status=state.status.value,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


def _state_to_summary(state: EnterpriseRunState) -> RunSummaryView:
    return RunSummaryView(
        run_id=state.run_id,
        tenant_id=state.tenant_id,
        task_type=state.task_type.value,
        status=state.status.value,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


def _list_checkpoints_from_artifacts(
    sac_root: Path,
    *,
    tenant_id: str,
    status: str | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[RunSummaryView], str | None]:
    root = runs_root(sac_root)
    summaries: list[RunSummaryView] = []
    if not root.is_dir():
        return summaries, None
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        try:
            validate_run_id(child.name)
            checkpoint = load_checkpoint(sac_root, child.name)
        except Exception:
            continue
        summary = _checkpoint_to_summary(checkpoint)
        if summary.tenant_id != tenant_id:
            continue
        if status is not None and summary.status != status:
            continue
        summaries.append(summary)
    summaries.sort(key=lambda item: (item.updated_at, item.run_id), reverse=True)
    if cursor:
        summaries = [item for item in summaries if item.run_id < cursor]
    page = summaries[:limit]
    next_cursor = summaries[limit].run_id if len(summaries) > limit else None
    return page, next_cursor


def list_runs(
    backend: PersistenceBackend,
    *,
    tenant_id: str,
    status: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[RunSummaryView], str | None]:
    tenant = validate_tenant_id(tenant_id)
    bounded_limit = max(1, min(limit, 200))
    if _is_postgres_backend(backend):
        with backend._uow.connection() as conn:
            params: list[Any] = [tenant]
            filters = ["tenant_id = %s"]
            if status is not None:
                filters.append("state->>'status' = %s")
                params.append(status)
            if cursor:
                filters.append("run_id < %s")
                params.append(cursor)
            params.append(bounded_limit + 1)
            rows = conn.execute(
                f"""
                SELECT state
                FROM enterprise.checkpoints
                WHERE {' AND '.join(filters)}
                ORDER BY updated_at DESC, run_id DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        summaries = [_state_to_summary(EnterpriseRunState.model_validate(row[0])) for row in rows]
        next_cursor = summaries[bounded_limit].run_id if len(summaries) > bounded_limit else None
        return summaries[:bounded_limit], next_cursor
    return _list_checkpoints_from_artifacts(
        artifacts_root(backend),
        tenant_id=tenant,
        status=status,
        limit=bounded_limit,
        cursor=cursor,
    )


def get_run(
    backend: PersistenceBackend,
    *,
    tenant_id: str,
    run_id: str,
) -> RunSummaryView:
    checkpoint = backend.runs.load_checkpoint(tenant_id=tenant_id, run_id=run_id)
    return _checkpoint_to_summary(checkpoint)


def list_approvals(
    backend: PersistenceBackend,
    *,
    tenant_id: str,
    status: str | None = None,
) -> list[ApprovalRequest]:
    tenant = validate_tenant_id(tenant_id)
    if _is_postgres_backend(backend):
        with backend._uow.connection() as conn:
            params: list[Any] = [tenant]
            filters = ["tenant_id = %s"]
            if status is not None:
                filters.append("status = %s")
                params.append(status)
            rows = conn.execute(
                f"""
                SELECT payload
                FROM enterprise.approval_requests
                WHERE {' AND '.join(filters)}
                ORDER BY created_at DESC, request_id DESC
                LIMIT 200
                """,
                tuple(params),
            ).fetchall()
        return [ApprovalRequest.model_validate(row[0]) for row in rows]
    sac_root = artifacts_root(backend)
    root = runs_root(sac_root)
    items: list[ApprovalRequest] = []
    if not root.is_dir():
        return items
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        try:
            run_id = child.name
            validate_run_id(run_id)
            checkpoint = load_checkpoint(sac_root, run_id)
            if checkpoint.state.tenant_id != tenant:
                continue
            for request in list_requests(sac_root, run_id):
                if request.tenant_id != tenant:
                    continue
                if status is not None and request.status != status:
                    continue
                items.append(request)
        except Exception:
            continue
    items.sort(key=lambda item: (item.created_at, item.request_id), reverse=True)
    return items[:200]


def build_run_timeline(
    backend: PersistenceBackend,
    *,
    tenant_id: str,
    run_id: str,
) -> RunTimeline:
    backend.runs.load_checkpoint(tenant_id=tenant_id, run_id=run_id)
    return build_timeline(artifacts_root(backend), run_id)


def list_redacted_trace_events(
    backend: PersistenceBackend,
    *,
    tenant_id: str,
    run_id: str,
) -> list[dict[str, str]]:
    backend.runs.load_checkpoint(tenant_id=tenant_id, run_id=run_id)
    events = backend.trace.list_events(tenant_id=tenant_id, run_id=run_id)
    return [_export_trace_event(event) for event in events]


def _export_trace_event(event: TraceEvent) -> dict[str, str]:
    payload = {key: value for key, value in event.payload.items() if isinstance(value, str)}
    apply_profile_to_payload(payload, profile=DEFAULT_TRACE_EXPORT_PROFILE)
    event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
    return {
        "event_type": event_type,
        "timestamp": event.timestamp,
    }


def list_eval_baselines(baselines_root: Path | None) -> list[dict[str, str]]:
    if baselines_root is None or not baselines_root.is_dir():
        return []
    suites = sorted(
        {
            path.stem.rsplit("_v", 1)[0]
            for path in baselines_root.glob("*_v*.json")
            if path.is_file()
        }
    )
    items: list[dict[str, str]] = []
    for suite in suites:
        baseline_path = baseline_path_for_suite(baselines_root, suite)
        if baseline_path is None or not baseline_path.is_file():
            continue
        items.append({"suite": suite, "baseline_id": baseline_path.stem})
    return items


def run_detail_payload(summary: RunSummaryView, *, tenant_id: str) -> dict[str, str]:
    return {
        "run_id": summary.run_id,
        "tenant_id": summary.tenant_id,
        "task_type": summary.task_type,
        "status": summary.status,
        "created_at": summary.created_at,
        "updated_at": summary.updated_at,
        "status_url": f"/v2/runs/{summary.run_id}?tenant_id={tenant_id}",
    }


def timeline_payload(timeline: RunTimeline) -> dict[str, object]:
    events = [
        {
            "event_type": f"node.{node.name}",
            "timestamp": node.ended_at,
            "summary": node.summary,
        }
        for node in timeline.nodes
    ]
    return {"run_id": timeline.run_id, "events": events}


def trace_payload(run_id: str, events: list[dict[str, str]]) -> dict[str, object]:
    return {
        "run_id": run_id,
        "redaction_profile": DEFAULT_TRACE_EXPORT_PROFILE,
        "events": events,
    }


def approval_summary_payload(request: ApprovalRequest) -> dict[str, str]:
    return {
        "approval_id": request.request_id,
        "run_id": request.run_id,
        "tenant_id": request.tenant_id,
        "status": request.status,
        "created_at": request.created_at,
    }
