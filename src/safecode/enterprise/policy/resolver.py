"""Policy layer resolver with precedence and no-weakening enforcement."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from safecode.enterprise.policy.models import (
    ApprovalTier,
    PolicyLayer,
    PolicyLayerName,
    PolicyOverrideBlocked,
    PolicySnapshot,
    PolicyValue,
    is_approval_tier,
    is_weakening,
    normalize_policy_key,
)

LAYER_PRIORITY: dict[PolicyLayerName, int] = {
    "workflow": 0,
    "env": 1,
    "project": 2,
    "user": 3,
    "org": 4,
}

DEFAULT_ORG_POLICY: dict[str, ApprovalTier | str | bool | list[str]] = {
    "file_write": "GATE",
    "command_execute": "GATE",
    "scanner_run": "CONFIRM",
    "github_read": "AUTO",
    "github_write_comment": "GATE",
    "github_branch_push": "BLOCK",
    "github_pr_create": "GATE",
    "issue_comment": "GATE",
    "mcp_read": "CONFIRM",
    "mcp_write": "BLOCK",
    "retrieval_source_access": "AUTO",
    "memory_fact_inject": "AUTO",
    "policy_config_change": "BLOCK",
    "production_access": "BLOCK",
    "allow_as_role_flag": False,
    "allow_debug_traces": False,
    "protected_branches": ["main", "master", "trunk", "release/*"],
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _layer_values(raw: dict[str, Any], *, layer: PolicyLayerName, source_ref: str) -> PolicyLayer:
    values: dict[str, PolicyValue] = {}
    for key, value in raw.items():
        normalized = normalize_policy_key(key)
        if isinstance(value, dict):
            tier = str(value.get("value", value.get("tier", "")))
            rationale = value.get("rationale")
        else:
            tier = str(value)
            rationale = None
        values[normalized] = PolicyValue(
            key=normalized,
            value=tier,
            rationale=rationale or f"set by {layer} layer ({source_ref})",
        )
    return PolicyLayer(name=layer, source_ref=source_ref, values=values)


def _load_yaml_policy(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    policies = payload.get("policies", payload)
    if not isinstance(policies, dict):
        return {}
    return policies


def load_env_policy() -> PolicyLayer:
    values: dict[str, PolicyValue] = {}
    prefix = "SAC_ENTERPRISE_"
    for env_key, env_value in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        policy_key = normalize_policy_key(env_key[len(prefix) :].lower())
        values[policy_key] = PolicyValue(
            key=policy_key,
            value=env_value,
            rationale=f"set by env layer ({env_key})",
        )
    return PolicyLayer(name="env", source_ref=prefix, values=values)


def default_org_layer() -> PolicyLayer:
    return _layer_values(
        dict(DEFAULT_ORG_POLICY),
        layer="org",
        source_ref="builtin-default-org-policy",
    )


def load_org_layer(config_root: Path | None = None) -> PolicyLayer:
    root = config_root or Path.home() / ".config" / "safecode" / "enterprise"
    path = root / "org.yaml"
    if not path.is_file():
        return default_org_layer()
    return _layer_values(_load_yaml_policy(path), layer="org", source_ref=str(path))


def load_user_layer(config_root: Path | None = None) -> PolicyLayer:
    root = config_root or Path.home() / ".config" / "safecode" / "enterprise"
    path = root / "user.yaml"
    return _layer_values(_load_yaml_policy(path), layer="user", source_ref=str(path))


def load_project_layer(repo_root: Path) -> PolicyLayer:
    path = repo_root / ".sac" / "enterprise" / "project.yaml"
    return _layer_values(_load_yaml_policy(path), layer="project", source_ref=str(path))


def workflow_layer(overrides: dict[str, Any] | None) -> PolicyLayer:
    return _layer_values(dict(overrides or {}), layer="workflow", source_ref="cli-workflow-overrides")


def merge_layers(layers: list[PolicyLayer]) -> tuple[dict[str, PolicyValue], tuple[PolicyOverrideBlocked, ...]]:
    by_key: dict[str, list[tuple[int, PolicyLayerName, PolicyValue]]] = {}
    for layer in layers:
        priority = LAYER_PRIORITY[layer.name]
        for key, value in layer.values.items():
            by_key.setdefault(key, []).append((priority, layer.name, value))

    merged: dict[str, PolicyValue] = {}
    blocked: list[PolicyOverrideBlocked] = []
    for key, entries in by_key.items():
        winner_priority, winner_layer, winner_value = max(entries, key=lambda item: item[0])
        merged[key] = winner_value.model_copy(
            update={"rationale": winner_value.rationale or f"won from {winner_layer} layer"}
        )
        if not is_approval_tier(str(winner_value.value)):
            continue
        final_tier = str(winner_value.value)
        for priority, layer_name, candidate in entries:
            if priority >= winner_priority:
                continue
            attempted = str(candidate.value)
            if not is_approval_tier(attempted):
                continue
            if is_weakening(final_tier, attempted):  # type: ignore[arg-type]
                blocked.append(
                    PolicyOverrideBlocked(
                        key=key,
                        attempted_value=attempted,
                        final_value=final_tier,
                        layer=layer_name,
                    )
                )
    return merged, tuple(blocked)


def snapshot_id_for(layers: list[PolicyLayer], merged: dict[str, PolicyValue]) -> str:
    payload = {
        "layers": [layer.model_dump(mode="json") for layer in layers],
        "merged": {key: value.model_dump(mode="json") for key, value in sorted(merged.items())},
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"snapshot-{digest[:16]}"


class PolicyResolver:
    """Resolve policy layers into an immutable snapshot."""

    def __init__(
        self,
        *,
        repo_root: Path,
        config_root: Path | None = None,
        workflow_overrides: dict[str, Any] | None = None,
        extra_layers: list[PolicyLayer] | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.config_root = config_root
        self.workflow_overrides = workflow_overrides
        self.extra_layers = list(extra_layers or [])

    def collect_layers(self) -> list[PolicyLayer]:
        ordered = [
            workflow_layer(self.workflow_overrides),
            load_env_policy(),
            load_project_layer(self.repo_root),
            load_user_layer(self.config_root),
            load_org_layer(self.config_root),
        ]
        ordered.extend(self.extra_layers)
        return sorted(ordered, key=lambda layer: LAYER_PRIORITY[layer.name])

    def resolve(self, *, tenant_id: str = "local") -> PolicySnapshot:
        layers = self.collect_layers()
        merged, blocked = merge_layers(layers)
        created_at = _utc_now()
        snapshot_id = snapshot_id_for(layers, merged)
        return PolicySnapshot(
            snapshot_id=snapshot_id,
            tenant_id=tenant_id,
            layers=tuple(layers),
            merged=merged,
            created_at=created_at,
            blocked_overrides=blocked,
        )


def resolve_policy(
    repo_root: Path,
    *,
    config_root: Path | None = None,
    workflow_overrides: dict[str, Any] | None = None,
    extra_layers: list[PolicyLayer] | None = None,
    tenant_id: str = "local",
) -> PolicySnapshot:
    return PolicyResolver(
        repo_root=repo_root,
        config_root=config_root,
        workflow_overrides=workflow_overrides,
        extra_layers=extra_layers,
    ).resolve(tenant_id=tenant_id)


def policy_tier(snapshot: PolicySnapshot, action_key: str, *, default: ApprovalTier = "GATE") -> ApprovalTier:
    key = normalize_policy_key(action_key)
    value = snapshot.merged.get(key)
    if value is None:
        return default
    tier = str(value.value)
    if is_approval_tier(tier):
        return tier  # type: ignore[return-value]
    return default


def policy_bool(snapshot: PolicySnapshot, key: str, *, default: bool = False) -> bool:
    normalized = normalize_policy_key(key)
    value = snapshot.merged.get(normalized)
    if value is None:
        return default
    if isinstance(value.value, bool):
        return value.value
    return str(value.value).strip().lower() in {"1", "true", "yes", "on"}
