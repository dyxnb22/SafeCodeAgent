"""Checkpoint persistence for enterprise workflow runs."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safecode.enterprise.workflow.exceptions import (
    CheckpointCorruptedError,
    CheckpointNotFoundError,
    InvalidRunIdError,
    InvalidStateSchemaVersionError,
)
from safecode.enterprise.workflow.ids import validate_run_id
from safecode.enterprise.workflow.nodes.registry import WORKFLOW_NODE_ORDER
from safecode.enterprise.workflow.state import (
    STATE_SCHEMA_VERSION,
    EnterpriseRunState,
    SUPPORTED_STATE_SCHEMA_VERSIONS,
)

CHECKPOINT_SCHEMA_VERSION = "1.2.0"


@dataclass(frozen=True)
class RunCheckpoint:
    schema_version: str
    run_id: str
    completed_nodes: list[str]
    next_node: str | None
    state: EnterpriseRunState


def runs_root(sac_root: Path) -> Path:
    return sac_root / "enterprise" / "runs"


def run_dir(sac_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    root = runs_root(sac_root).resolve()
    target = (root / run_id).resolve()
    if target.parent != root:
        raise InvalidRunIdError(f"run path escapes runs root: {run_id!r}")
    return target


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def save_checkpoint(sac_root: Path, checkpoint: RunCheckpoint) -> None:
    directory = run_dir(sac_root, checkpoint.run_id)
    payload = {
        "schema_version": checkpoint.schema_version,
        "run_id": checkpoint.run_id,
        "completed_nodes": list(checkpoint.completed_nodes),
        "next_node": checkpoint.next_node,
        "state": json.loads(checkpoint.state.model_dump_json()),
    }
    _atomic_write_json(directory / "state.json", payload)
    if checkpoint.completed_nodes:
        last_node = checkpoint.completed_nodes[-1]
        index = WORKFLOW_NODE_ORDER.index(last_node)
        node_path = directory / f"node_{index:02d}_{last_node}.json"
        _atomic_write_json(
            node_path,
            {
                "schema_version": checkpoint.schema_version,
                "run_id": checkpoint.run_id,
                "node_name": last_node,
                "completed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
        )


def load_checkpoint(sac_root: Path, run_id: str) -> RunCheckpoint:
    path = run_dir(sac_root, run_id) / "state.json"
    if not path.is_file():
        raise CheckpointNotFoundError(f"missing checkpoint for run {run_id!r}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckpointCorruptedError(f"checkpoint JSON corrupt for {run_id!r}") from exc
    if not isinstance(raw, dict):
        raise CheckpointCorruptedError(f"checkpoint root must be object for {run_id!r}")
    schema_version = raw.get("schema_version")
    if schema_version not in {CHECKPOINT_SCHEMA_VERSION, *SUPPORTED_STATE_SCHEMA_VERSIONS}:
        raise InvalidStateSchemaVersionError(f"unsupported checkpoint schema {schema_version!r}")
    completed = raw.get("completed_nodes")
    if not isinstance(completed, list) or not all(isinstance(item, str) for item in completed):
        raise CheckpointCorruptedError("completed_nodes must be a list of strings")
    if completed != list(completed):
        raise CheckpointCorruptedError("completed_nodes order mismatch")
    if completed != list(WORKFLOW_NODE_ORDER[: len(completed)]):
        raise CheckpointCorruptedError("completed_nodes sequence invalid")
    state_payload = raw.get("state")
    if not isinstance(state_payload, dict):
        raise CheckpointCorruptedError("checkpoint missing state object")
    state = EnterpriseRunState.model_validate(state_payload)
    next_node = raw.get("next_node")
    if next_node is not None and next_node not in WORKFLOW_NODE_ORDER:
        raise CheckpointCorruptedError(f"unknown next_node {next_node!r}")
    return RunCheckpoint(
        schema_version=str(schema_version),
        run_id=validate_run_id(str(raw.get("run_id", run_id))),
        completed_nodes=list(completed),
        next_node=next_node,
        state=state,
    )


def gc_runs(sac_root: Path, *, tenant_id: str, older_than_days: int) -> list[str]:
    from safecode.enterprise.persistence.protocols import assert_tenant_match, validate_tenant_id
    from safecode.enterprise.persistence.run_artifact_lock import run_artifact_lock

    tenant = validate_tenant_id(tenant_id)
    if older_than_days < 1:
        raise ValueError("older_than_days must be at least 1")
    root = runs_root(sac_root)
    if not root.is_dir():
        return []
    cutoff = datetime.now(timezone.utc).timestamp() - (older_than_days * 86400)
    removed: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.is_symlink():
            continue
        try:
            validate_run_id(child.name)
        except InvalidRunIdError:
            continue
        if child.resolve().parent != root.resolve():
            continue
        with run_artifact_lock(sac_root, tenant_id=tenant, run_id=child.name):
            if not child.is_dir() or child.is_symlink():
                continue
            state_path = child / "state.json"
            if not state_path.is_file():
                continue
            try:
                checkpoint = load_checkpoint(sac_root, child.name)
                assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="gc_runs")
            except Exception:
                continue
            if child.stat().st_mtime >= cutoff:
                continue
            try:
                shutil.rmtree(child)
            except OSError:
                continue
            removed.append(child.name)
    return removed
