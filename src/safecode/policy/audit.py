"""Policy audit helpers for presets, aliases, and safety invariants.

中文模块说明：策略预设审计与 diff 辅助。
- 校验 KNOWN_POLICY_NAMES、遗留别名、预设不变量（block_high_risk、restrict_to_project_root、network_enabled）。
- 未知项目/环境策略名记录为 issue，不信任未知配置。
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from safecode.config import (
    KNOWN_POLICY_NAMES,
    POLICY_PRESETS,
    SafeCodeConfig,
    is_known_policy_name,
    normalize_policy_name,
)
from safecode.core.diagnostic import Diagnostic


@dataclass(frozen=True)
class PolicyAuditResult:
    """Structured result of a policy audit.

    策略审计结构化结果；``ok`` 为真表示无 issues。
    """

    known_names: list[str]
    aliases_ok: bool
    preset_invariants_ok: bool
    project_policy: str | None
    env_policy: str | None
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_diagnostics(self) -> list[Diagnostic]:
        """Return typed diagnostics describing this audit."""
        return [
            Diagnostic.from_bool(
                "policy_known_names",
                bool(self.known_names),
                ", ".join(self.known_names),
            ),
            Diagnostic.from_bool(
                "policy_aliases",
                self.aliases_ok,
                "aliases normalised" if self.aliases_ok else "aliases broken",
            ),
            Diagnostic.from_bool(
                "policy_preset_invariants",
                self.preset_invariants_ok,
                "preset invariants ok"
                if self.preset_invariants_ok
                else "preset invariants broken",
            ),
            Diagnostic.from_bool(
                "policy_audit",
                self.ok,
                "policy audit passed" if self.ok else "; ".join(self.issues),
            ),
        ]


@dataclass(frozen=True)
class PolicyDiffEntry:
    """One effective-config knob delta against a named preset."""

    knob: str
    effective: object
    preset: object
    matches: bool


@dataclass(frozen=True)
class PolicyDiffResult:
    """Structured policy diff result."""

    against: str
    entries: list[PolicyDiffEntry]

    @property
    def has_differences(self) -> bool:
        return any(not entry.matches for entry in self.entries)

    def to_dict(self) -> dict:
        return {
            "against": self.against,
            "has_differences": self.has_differences,
            "entries": [
                {
                    "knob": entry.knob,
                    "effective": entry.effective,
                    "preset": entry.preset,
                    "matches": entry.matches,
                }
                for entry in self.entries
            ],
        }


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
    """检查所有预设是否满足内核安全不变量。"""
    issues: list[str] = []
    for name, preset in sorted(POLICY_PRESETS.items()):
        if preset.get("block_high_risk") is not True:
            issues.append(f"{name}: block_high_risk must be true.")
        if preset.get("restrict_to_project_root") is not True:
            issues.append(f"{name}: restrict_to_project_root must be true.")
        if preset.get("network_enabled") is not False:
            # 预设默认必须关闭网络，防止发布配置意外放宽。
            issues.append(f"{name}: network_enabled must be false by default.")
    return issues


_DIFF_KNOBS = (
    ("hooks.allow_medium_after_apply", "allow_medium_after_apply"),
    ("sandbox.network_allowlist", "network_allowlist"),
    ("sandbox.network_enabled", "network_enabled"),
    ("sandbox.restrict_to_project_root", "restrict_to_project_root"),
    ("shell.allow_readonly_without_confirm", "allow_readonly_without_confirm"),
    ("shell.allowed_commands", "allowed_commands"),
    ("shell.block_high_risk", "block_high_risk"),
    ("shell.require_confirm_for_medium", "require_confirm_for_medium"),
)


def diff_policy(project_root: Path, against: str) -> PolicyDiffResult:
    """Compare effective policy knobs with a named preset."""
    canonical = normalize_policy_name(against)
    preset = POLICY_PRESETS.get(canonical)
    if preset is None:
        raise ValueError(f"Unknown policy preset: {against!r}.")
    config = SafeCodeConfig.load(project_root)
    entries: list[PolicyDiffEntry] = []
    for knob, preset_key in _DIFF_KNOBS:
        effective = _effective_knob(config, knob)
        preset_value = _normalize_diff_value(preset[preset_key])
        effective_value = _normalize_diff_value(effective)
        entries.append(
            PolicyDiffEntry(
                knob=knob,
                effective=effective_value,
                preset=preset_value,
                matches=effective_value == preset_value,
            )
        )
    return PolicyDiffResult(against=canonical, entries=entries)


def _effective_knob(config: SafeCodeConfig, knob: str) -> object:
    current: object = config
    for part in knob.split("."):
        current = getattr(current, part)
    return current


def _normalize_diff_value(value: object) -> object:
    if isinstance(value, list):
        return sorted(str(item) for item in value)
    return value


def render_policy_diff(result: PolicyDiffResult) -> str:
    """Render deterministic policy diff output."""
    lines = [
        "SafeCode Policy Diff",
        "====================",
        f"Against: {result.against}",
        f"Differences: {'yes' if result.has_differences else 'no'}",
        "",
        "Knobs:",
    ]
    for entry in result.entries:
        marker = "!=" if not entry.matches else "=="
        lines.append(f"  {entry.knob}: {entry.effective!r} {marker} {entry.preset!r}")
    return "\n".join(lines)


def audit_policy(project_root: Path, *, env_policy: str | None = None) -> PolicyAuditResult:
    """Audit policy names, aliases, project/env values, and preset invariants.

    审计策略名、别名、项目/环境配置与预设不变量；未知策略名记入 issues 且不会被信任。
    """
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
        # 环境变量中的未知策略名应被忽略，避免通过 SAFECODE_POLICY 注入弱化配置。
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
