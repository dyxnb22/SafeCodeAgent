"""Compose profile validation for the v2.1 Team Server dev stack (v2.1.7-T2)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "compose.enterprise.yaml"
ENV_EXAMPLE = ROOT / "compose" / "enterprise.dev.env.example"


def _load_compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def test_compose_file_declares_api_worker_and_postgres() -> None:
    services = _load_compose()["services"]
    assert {"postgres", "api", "worker"} <= set(services)


def test_compose_binds_services_to_loopback_only() -> None:
    services = _load_compose()["services"]
    for name in ("postgres", "api"):
        ports = services[name].get("ports", [])
        assert ports, f"{name} must expose a loopback port"
        assert all(str(item).startswith("127.0.0.1:") for item in ports)


def test_compose_has_no_docker_socket_mounts() -> None:
    services = _load_compose()["services"]
    for name, service in services.items():
        for mount in service.get("volumes", []):
            assert "docker.sock" not in str(mount), f"{name} must not mount the Docker socket"


def test_compose_services_define_healthchecks() -> None:
    services = _load_compose()["services"]
    for name in ("postgres", "api"):
        assert "healthcheck" in services[name], f"{name} requires a healthcheck"


def test_compose_example_env_documents_required_credentials() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    required = (
        "SAC_ENTERPRISE_DATABASE_URL",
        "SAC_ENTERPRISE_OIDC_ISSUER",
        "SAC_ENTERPRISE_OIDC_AUDIENCE",
        "SAC_ENTERPRISE_OIDC_JWKS_PATH",
        "POSTGRES_PASSWORD",
    )
    for key in required:
        assert key in text


def test_compose_config_validates_when_env_file_exists(tmp_path: Path) -> None:
    env_file = tmp_path / "enterprise.dev.env"
    env_file.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    compose_copy = tmp_path / "compose.yaml"
    document = _load_compose()
    for service in document["services"].values():
        service["env_file"] = [str(env_file.name)]
    compose_copy.write_text(yaml.safe_dump(document), encoding="utf-8")
    if not shutil_which("docker"):
        pytest.skip("docker not available")
    subprocess.run(
        ["docker", "compose", "-f", str(compose_copy), "config"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )


def test_missing_env_file_is_not_committed() -> None:
    assert not (ROOT / "compose" / "enterprise.dev.env").exists()


def shutil_which(name: str) -> str | None:
    from shutil import which

    return which(name)
