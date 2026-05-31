"""MCP write proposal models and persistence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.context.redactor import redact_secrets
from safecode.utils.time import utc_now_iso


class MCPWriteProposal(BaseModel):
    """A pending MCP write proposal stored before execution."""

    proposal_id: str
    server: str
    tool: str
    classification: str
    input_payload: dict = Field(default_factory=dict)
    input_hash: str
    created_at: str
    status: str = "pending"
    risk_level: str
    reason: str


class MCPWriteProposalStore:
    """Persist and manage the single pending MCP write proposal."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self._pending_path = project_root / self.config.sac_dir / "pending_mcp_call.json"

    @property
    def pending_path(self) -> Path:
        return self._pending_path

    def create(
        self,
        server: str,
        tool: str,
        input_data: dict,
        classification: str,
        reason: str,
    ) -> MCPWriteProposal:
        """Create a new pending proposal. Fails if one already exists."""
        if self._pending_path.exists():
            if self.load_pending() is None:
                raise FileExistsError(
                    "A pending MCP write proposal exists but cannot be parsed. "
                    "Discard it first with 'sac mcp discard'."
                )
            raise FileExistsError(
                "A pending MCP write proposal already exists. "
                "Discard it first with 'sac mcp discard'."
            )

        limited_input = self._size_limit_input(input_data)
        redacted_input = self._redact_input(limited_input)
        input_hash = self._hash_input(redacted_input)

        proposal = MCPWriteProposal(
            proposal_id=str(uuid4()),
            server=server,
            tool=tool,
            classification=classification,
            input_payload=redacted_input,
            input_hash=input_hash,
            created_at=utc_now_iso(),
            status="pending",
            risk_level=self._risk_level(classification),
            reason=reason,
        )
        self._write(proposal)
        return proposal

    def load_pending(self) -> MCPWriteProposal | None:
        """Return the current pending proposal, or None."""
        if not self._pending_path.exists():
            return None
        try:
            data = json.loads(self._pending_path.read_text(encoding="utf-8"))
            return MCPWriteProposal(**data)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def approve_pending(self, proposal_id: str) -> MCPWriteProposal:
        """Mark the pending proposal as approved. Raises PermissionError on mismatch."""
        proposal = self.load_pending()
        if proposal is None:
            raise PermissionError("No pending MCP write proposal to approve.")
        if proposal.proposal_id != proposal_id:
            raise PermissionError("Proposal ID mismatch — cannot approve.")
        if proposal.status != "pending":
            raise PermissionError(f"Proposal is not in pending status: {proposal.status}")
        approved = proposal.model_copy(update={"status": "approved"})
        self._write(approved)
        return approved

    def reject_pending(self, proposal_id: str) -> MCPWriteProposal:
        """Mark the pending proposal as rejected. Raises PermissionError on mismatch."""
        proposal = self.load_pending()
        if proposal is None:
            raise PermissionError("No pending MCP write proposal to reject.")
        if proposal.proposal_id != proposal_id:
            raise PermissionError("Proposal ID mismatch — cannot reject.")
        rejected = proposal.model_copy(update={"status": "rejected"})
        self._write(rejected)
        return rejected

    def discard_pending(self) -> bool:
        """Remove the pending proposal file. Returns True if one existed."""
        if self._pending_path.exists():
            self._pending_path.unlink()
            return True
        return False

    def _write(self, proposal: MCPWriteProposal) -> None:
        self._pending_path.parent.mkdir(parents=True, exist_ok=True)
        self._pending_path.write_text(
            json.dumps(proposal.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _size_limit_input(self, input_data: dict) -> dict:
        serialized = json.dumps(input_data, ensure_ascii=False)
        if len(serialized) <= self.config.max_context_chars:
            return input_data
        raise PermissionError("MCP write proposal input exceeded size limits.")

    def _redact_input(self, input_data: dict) -> dict:
        raw = json.dumps(input_data, ensure_ascii=False)
        redacted_text = redact_secrets(raw)
        if redacted_text == raw:
            return input_data
        return {"_redacted": True, "_payload": redacted_text}

    @staticmethod
    def hash_input(input_data: dict) -> str:
        """Hash an input dict using the same algorithm used when creating proposals."""
        payload = json.dumps(input_data, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _hash_input(self, input_data: dict) -> str:
        return self.hash_input(input_data)

    @staticmethod
    def _risk_level(classification: str) -> str:
        if classification == "write":
            return "high"
        if classification == "unknown":
            return "critical"
        return "low"
