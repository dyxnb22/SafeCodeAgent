"""Policy audit helpers for presets, aliases, and safety invariants."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from safecode.config import (
    KNOWN_POLICY_NAMES,
    POLICY_PRESETS,
    is_known_policy_name,
    normalize_policy_name,
)


@dataclass(frozen=True)
class PolicyAuditResult:
    """Structured result of a policy audit."""

    known_names: list[str]
    aliases_ok: bool
    preset_invariants_ok: bool
    project_policy: str | None
    env_policy: str | None
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def _read_project_policy(project_root: Path) -> str | None:
    path = project_root / ".sac" / "config.toml"
    if not path.is_file():
        return None
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        value = data.get("policy")
        return value if isinstance(value, str) else None
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _preset_invariant_issues() -> list[str]:
    issues: list[str] = []
    for name, preset in sorted(POLICY_PRESETS.items()):
        if preset.get("block_high_risk") is not True:
            issues.append(f"{name}: block_high_risk must be true.")
        if preset.get("restrict_to_project_root") is not True:
            issues.append(f"{name}: restrict_to_project_root must be true.")
        if preset.get("network_enabled") is not False:
            issues.append(f"{name}: network_enabled must be false by default.")
    return issues


def audit_policy(project_root: Path, *, env_policy: str | None = None) -> PolicyAuditResult:
    """Audit policy names, aliases, project/env values, and preset invariants."""
    env_value = env_policy if env_policy is not None else os.getenv("SAFECODE_POLICY")
    project_policy = _read_project_policy(project_root)
    issues: list[str] = []

    expected = {"strict", "balanced", "experimental", "normal", "learning"}
    missing = expected - KNOWN_POLICY_NAMES
    if missing:
        issues.append(f"KNOWN_POLICY_NAMES missing: {sorted(missing)}.")

    aliases_ok = (
        normalize_policy_name("normal") == "balanced"
        and normalize_policy_name("learning") == "experimental"
    )
    if not aliases_ok:
        issues.append("Legacy aliases are not normalized correctly.")

    preset_issues = _preset_invariant_issues()
    issues.extend(preset_issues)

    if project_policy is not None and not is_known_policy_name(project_policy):
        issues.append(f"Project policy {project_policy!r} is unknown and will not be trusted.")
    if env_value and not is_known_policy_name(env_value):
        issues.append(f"SAFECODE_POLICY {env_value!r} is unknown and will be ignored.")

    return PolicyAuditResult(
        known_names=sorted(KNOWN_POLICY_NAMES),
        aliases_ok=aliases_ok,
        preset_invariants_ok=not preset_issues,
        project_policy=project_policy,
        env_policy=env_value,
        issues=issues,
    )


def render_policy_audit(result: PolicyAuditResult) -> str:
    """Render policy audit output."""
    status = "PASS" if result.ok else "FAIL"
    lines = [
        "SafeCode Policy Audit",
        "=====================",
        f"Status: {status}",
        "",
        f"  known names          : {', '.join(result.known_names)}",
        f"  aliases ok           : {'yes' if result.aliases_ok else 'NO'}",
        f"  preset invariants    : {'yes' if result.preset_invariants_ok else 'NO'}",
        f"  project policy       : {result.project_policy or '(none)'}",
        f"  SAFECODE_POLICY      : {result.env_policy or '(none)'}",
        "",
    ]
    if result.issues:
        lines.append("Issues:")
        lines.extend(f"  {issue}" for issue in result.issues)
        lines.append("Next steps:")
        lines.append("  Fix unknown policy names or broken preset invariants, then rerun sac config policy-audit.")
    else:
        lines.append("Policy audit passed.")
        lines.append("Next steps:")
        lines.append("  No policy follow-up needed.")
    return "\n".join(lines)
