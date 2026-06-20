"""Proposal file digest helpers for approval target binding."""

from __future__ import annotations

import hashlib
from pathlib import Path

from safecode.enterprise.workflow.state import Proposal


def proposal_ref_sha256(proposal_ref: str) -> str:
    """Compute SHA-256 of the proposal reference file contents."""
    path = Path(proposal_ref)
    if not path.is_file():
        raise FileNotFoundError(f"proposal ref file missing: {proposal_ref!r}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proposal_digest(proposal: Proposal | None) -> str:
    if proposal is None:
        return ""
    return proposal_ref_sha256(proposal.ref)


def merge_proposal_sha256(target: dict[str, str], proposal_ref: str) -> dict[str, str]:
    """Merge a proposal digest into an approval target with stable key order."""
    return dict(sorted({**target, "proposal_sha256": proposal_ref_sha256(proposal_ref)}.items()))
