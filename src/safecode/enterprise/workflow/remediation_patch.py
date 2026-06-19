"""Remediation patch apply with checkpoint and rollback."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from safecode.checkpoint.manager import CheckpointManager
from safecode.patch.applier import PatchApplier
from safecode.patch.models import PatchProposal


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_patch_proposal(run_dir: Path, proposal: PatchProposal) -> Path:
    path = run_dir / "patch_proposal.json"
    path.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_patch_proposal(path: Path) -> PatchProposal:
    return PatchProposal.model_validate_json(path.read_text(encoding="utf-8"))


def apply_with_checkpoint(project_root: Path, proposal: PatchProposal) -> str:
    manager = CheckpointManager(project_root)
    metadata = manager.create(proposal)
    PatchApplier(project_root).apply(proposal)
    return metadata.checkpoint_id


def rollback_last(project_root: Path) -> str:
    metadata = CheckpointManager(project_root).rollback_last()
    return metadata.checkpoint_id
