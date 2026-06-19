"""v3.0 flagship demo bundle contract tests (v3.0.4-T1)."""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_DEMOS = _ROOT / "examples" / "enterprise" / "demos" / "v3.0"

_REQUIRED_DEMOS = (
    "pr_review_ga.md",
    "remediation_ga.md",
    "secure_planning_ga.md",
    "evidence_export_ga.md",
    "console_approval_ga.md",
    "security_check.md",
    "deployment_evidence.md",
)

_PATH_PATTERN = re.compile(r"`([^`]+\.(?:py|json|md|yaml|sh))`")


def test_v3_0_flagship_demo_bundle_is_complete() -> None:
    for name in _REQUIRED_DEMOS:
        assert (_DEMOS / name).is_file(), f"missing demo artifact: {name}"


def test_v3_0_demos_reference_existing_offline_targets() -> None:
    missing: list[str] = []
    for demo_path in sorted(_DEMOS.glob("*.md")):
        text = demo_path.read_text(encoding="utf-8")
        for match in _PATH_PATTERN.findall(text):
            candidate = match.strip()
            if candidate.startswith(("sac ", "bash ", "curl ", "docker ", "export ")):
                continue
            if candidate.startswith("GET ") or candidate.startswith("POST "):
                continue
            if "<" in candidate:
                continue
            if candidate.endswith(".json") and "/" not in candidate:
                candidate = f"tests/enterprise/contracts/snapshots/{candidate}"
            path = _ROOT / candidate
            if not path.exists():
                missing.append(f"{demo_path.name}: {candidate}")
    assert not missing, "missing referenced paths:\n" + "\n".join(missing)


def test_v3_0_demos_reference_ga_contract_tests() -> None:
    text = (_DEMOS / "pr_review_ga.md").read_text(encoding="utf-8")
    assert "test_public_contract_v3_0.py" in text
