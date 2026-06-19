"""v2.0 RC → v3.0 GA migration compatibility tests (v3.0.1-T1)."""

from __future__ import annotations

import json
from pathlib import Path

from safecode.enterprise.api.contracts import SERVICE_PLANE_PATHS, list_operation_ids, load_openapi_contract
from safecode.enterprise.api.settings import RuntimeMode, load_team_server_settings
from safecode.enterprise.contracts.snapshot import all_contracts
from safecode.enterprise.contracts.v3_0 import API_PATH_PREFIX, MIGRATION_FROM
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.persistence.postgres.migrate import list_migration_files

_SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
_V2_RC_PATHS = _SNAPSHOTS / "migration_v2_rc_service_plane.json"


def _load_v2_rc_service_plane() -> list[str]:
    payload = json.loads(_V2_RC_PATHS.read_text(encoding="utf-8"))
    return list(payload["service_plane_paths"])


def test_v2_0_rc_contract_snapshots_still_match_live() -> None:
    for name, contract in all_contracts().items():
        expected = json.loads((_SNAPSHOTS / f"{name}.json").read_text(encoding="utf-8"))
        assert contract == expected, f"v2.0 RC contract {name} drift breaks GA migration"


def test_v2_0_rc_local_settings_load_under_v3_0_ga() -> None:
    settings = load_team_server_settings(
        runtime_mode=RuntimeMode.LOCAL,
        operator_actor="local-dev",
    )
    assert settings.runtime_mode is RuntimeMode.LOCAL
    assert settings.operator_actor == "local-dev"
    assert settings.otel_enabled is False


def test_v2_0_rc_read_path_works_on_local_backend(tmp_path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    assert backend.probe() is True
    ok, reason = backend.audit.verify_integrity()
    assert ok is True, reason


def test_service_plane_paths_are_migration_compatible() -> None:
    v2_rc_paths = set(_load_v2_rc_service_plane())
    ga_paths = set(SERVICE_PLANE_PATHS)
    assert v2_rc_paths.issubset(ga_paths), "GA removed v2.0 RC service plane paths"


def test_openapi_operation_ids_are_migration_compatible() -> None:
    v2_rc = json.loads((_SNAPSHOTS / "migration_v2_rc_openapi.json").read_text(encoding="utf-8"))
    live_ids = set(list_operation_ids())
    assert set(v2_rc["operation_ids"]).issubset(live_ids)


def test_migration_bundle_is_deterministic() -> None:
    first = [version for version, _ in list_migration_files()]
    second = [version for version, _ in list_migration_files()]
    assert first == second
    assert first


def test_ga_contract_documents_v2_rc_migration_source() -> None:
    from safecode.enterprise.contracts.v3_0 import enterprise_ga_v3_0_contract

    live = enterprise_ga_v3_0_contract()
    assert live["migration_from"] == MIGRATION_FROM
    assert live["api_path_prefix"] == API_PATH_PREFIX


def test_openapi_contract_status_supported_at_ga() -> None:
    document = load_openapi_contract()
    assert document["info"]["x-contract-status"] == "supported"
