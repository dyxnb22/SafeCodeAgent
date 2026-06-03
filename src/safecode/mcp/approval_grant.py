"""MCP write approval grant store (v3.8.2).

Approvals are stored outside the project root so that project-local files
cannot forge their own approvals.  The directory is controlled by the user,
not by the project being edited.

Default location: ``~/.sac/mcp/approvals/`` (outside project root).
Override:        ``SAFECODE_MCP_APPROVAL_DIR`` env var.

Each grant is a single JSON file: ``{approval_dir}/{proposal_id}.json``.
Grants are single-use: ``consume()`` deletes the file after reading it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from safecode.utils.time import utc_now_iso

_DEFAULT_APPROVAL_SUBDIR = Path(".sac") / "mcp" / "approvals"


@dataclass(frozen=True)
class MCPWriteApprovalGrant:
    """An out-of-project grant that permits executing one write proposal."""

    proposal_id: str
    granted_at: str
    consumed: bool = False

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "granted_at": self.granted_at,
            "consumed": self.consumed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MCPWriteApprovalGrant":
        return cls(
            proposal_id=str(data["proposal_id"]),
            granted_at=str(data["granted_at"]),
            consumed=bool(data.get("consumed", False)),
        )


class MCPApprovalStore:
    """Store and consume single-use write approval grants outside the project root.

    The approval directory is intentionally outside the project tree so that
    project-controlled files cannot forge an approval.
    """

    def __init__(self) -> None:
        env_dir = os.environ.get("SAFECODE_MCP_APPROVAL_DIR")
        if env_dir:
            self._approval_dir = Path(env_dir)
        else:
            self._approval_dir = Path.home() / ".sac" / "mcp" / "approvals"

    @property
    def approval_dir(self) -> Path:
        return self._approval_dir

    def _grant_path(self, proposal_id: str) -> Path:
        return self._approval_dir / f"{proposal_id}.json"

    def grant(self, proposal_id: str) -> MCPWriteApprovalGrant:
        """Write a fresh, unconsumed approval grant for the given proposal.

        Raises ``PermissionError`` if a grant already exists for this proposal.
        """
        self._approval_dir.mkdir(parents=True, exist_ok=True)
        path = self._grant_path(proposal_id)
        if path.exists():
            raise PermissionError(
                f"An approval grant already exists for proposal '{proposal_id}'. "
                "Revoke or consume it first."
            )
        grant = MCPWriteApprovalGrant(
            proposal_id=proposal_id,
            granted_at=utc_now_iso(),
            consumed=False,
        )
        path.write_text(json.dumps(grant.to_dict(), ensure_ascii=False), encoding="utf-8")
        return grant

    def consume(self, proposal_id: str) -> MCPWriteApprovalGrant | None:
        """Read and permanently delete the grant (single-use).

        Returns the grant if it exists and is unconsumed, else ``None``.
        """
        path = self._grant_path(proposal_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            grant = MCPWriteApprovalGrant.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None
        if grant.consumed:
            return None
        # Single-use: delete immediately.
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return grant

    def has_valid_grant(self, proposal_id: str) -> bool:
        """Return True if an unconsumed grant exists for this proposal."""
        path = self._grant_path(proposal_id)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return not bool(data.get("consumed", False))
        except (json.JSONDecodeError, TypeError, ValueError):
            return False

    def revoke(self, proposal_id: str) -> bool:
        """Delete a grant without consuming it. Returns True if one existed."""
        path = self._grant_path(proposal_id)
        if not path.exists():
            return False
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            return False
