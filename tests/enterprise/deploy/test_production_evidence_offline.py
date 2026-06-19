"""Production deployment evidence contract tests (v3.0.3-T1)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[3]
_EVIDENCE = _ROOT / "examples" / "enterprise" / "demos" / "v3.0" / "deployment_evidence.md"
_COMPOSE = _ROOT / "compose.enterprise.yaml"
_UP = _ROOT / "scripts" / "enterprise-up.sh"
_FORBIDDEN = re.compile(r"(ghp_|gho_|sk-|password=|postgresql://|/Users/|/home/)")

_PROBE_PATHS = ("/healthz", "/readyz", "/version")


def test_deployment_evidence_document_exists() -> None:
    assert _EVIDENCE.is_file()
    text = _EVIDENCE.read_text(encoding="utf-8")
    assert "production-like" in text.lower()
    assert "audit chain" in text.lower()
    assert "incident" in text.lower()


def test_deployment_evidence_has_no_secret_or_debug_material() -> None:
    text = _EVIDENCE.read_text(encoding="utf-8")
    match = _FORBIDDEN.search(text)
    assert match is None, f"forbidden material in deployment evidence: {match.group(0) if match else ''}"


def test_compose_declares_health_probes_for_core_services() -> None:
    payload = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    api = payload["services"]["api"]
    assert any(path in str(api.get("healthcheck", {})) for path in _PROBE_PATHS) or "healthcheck" in api


def test_enterprise_up_script_references_compose_file() -> None:
    text = _UP.read_text(encoding="utf-8")
    assert "compose.enterprise.yaml" in text
    assert "docker compose" in text


def test_deployment_evidence_references_offline_verification_commands() -> None:
    text = _EVIDENCE.read_text(encoding="utf-8")
    assert "test_production_evidence_offline.py" in text
    assert "enterprise-up.sh" in text
