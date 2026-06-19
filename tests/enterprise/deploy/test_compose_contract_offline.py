"""Compose deployment contract tests (v2.5.6)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE = _ROOT / "compose.enterprise.yaml"
_UP_SCRIPT = _ROOT / "scripts" / "enterprise-up.sh"
_ROLLBACK_SCRIPT = _ROOT / "scripts" / "enterprise-rollback.sh"
_BACKUP_SCRIPT = _ROOT / "scripts" / "enterprise-backup.sh"
_ENV_EXAMPLE = _ROOT / "compose" / "enterprise.dev.env.example"


def test_compose_file_defines_core_services_with_healthchecks() -> None:
    payload = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    services = payload["services"]
    for name in ("postgres", "api", "worker"):
        assert name in services
        assert "healthcheck" in services[name], f"{name} missing healthcheck"
    assert "console" in services


def test_compose_config_is_valid(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker not available")
    if not _ENV_EXAMPLE.is_file():
        pytest.skip("compose env example missing")
    env_copy = tmp_path / "enterprise.dev.env"
    shutil.copy(_ENV_EXAMPLE, env_copy)
    compose_copy = tmp_path / "compose.enterprise.yaml"
    compose_copy.write_text(
        _COMPOSE.read_text(encoding="utf-8").replace(
            "compose/enterprise.dev.env", str(env_copy)
        ),
        encoding="utf-8",
    )
    subprocess.run(
        ["docker", "compose", "-f", str(compose_copy), "config"],
        check=True,
        capture_output=True,
        text=True,
    )


def test_deploy_scripts_exist_and_are_executable_bash() -> None:
    for script in (_UP_SCRIPT, _ROLLBACK_SCRIPT, _BACKUP_SCRIPT):
        assert script.is_file()
        first_line = script.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("#!/usr/bin/env bash")


def test_compose_uses_pgvector_capable_postgres_image() -> None:
    payload = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    image = payload["services"]["postgres"]["image"]
    assert image == "pgvector/pgvector:pg16"


def test_no_development_private_key_is_committed() -> None:
    assert not (_ROOT / "examples" / "enterprise" / "dev" / "signing-key.pem").exists()
    assert "compose/.enterprise-dev-oidc/" in (_ROOT / ".gitignore").read_text(encoding="utf-8")
