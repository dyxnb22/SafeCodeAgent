"""Markdown rendering for enterprise approval inbox."""

from __future__ import annotations

from datetime import datetime, timezone

from safecode.enterprise.approvals.store import ApprovalRequest


def _parse_created_at(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _format_age(created_at: str) -> str:
    created = _parse_created_at(created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - created
    minutes = max(int(delta.total_seconds() // 60), 0)
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def render_pending_requests(requests: list[ApprovalRequest]) -> str:
    pending = [item for item in requests if item.status == "pending"]
    if not pending:
        return "# Pending Approvals\n\nNo pending approval requests.\n"

    lines = ["# Pending Approvals", ""]
    lines.append("| Request ID | Action | Risk | Node | Requested By | Age |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in pending:
        lines.append(
            "| {id} | {action} | {risk} | {node} | {actor} | {age} |".format(
                id=item.request_id,
                action=item.action.value,
                risk=item.risk_tier.value,
                node=item.requested_by_node,
                actor=item.requesting_actor,
                age=_format_age(item.created_at),
            )
        )
    lines.append("")
    return "\n".join(lines)
