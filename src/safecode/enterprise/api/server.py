"""Uvicorn entrypoint for the Team Server (v2.1.7-T2)."""

from __future__ import annotations

import os
from pathlib import Path

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.dependencies import (
    build_backend,
    build_local_subject_resolver,
    build_oidc_validator_from_settings,
    fail_closed_subject_resolver,
)
from safecode.enterprise.api.settings import RuntimeMode, load_team_server_settings_from_env


def build_application():
    settings = load_team_server_settings_from_env()
    artifacts_root = Path(
        os.environ.get("SAC_ENTERPRISE_ARTIFACTS_ROOT", "/var/lib/safecode")
    )
    backend = build_backend(settings, sac_root=artifacts_root)
    oidc_validator = None
    subject_resolver = fail_closed_subject_resolver(settings)
    if settings.runtime_mode is RuntimeMode.SERVER:
        oidc_validator = build_oidc_validator_from_settings(settings)
        subject_resolver = fail_closed_subject_resolver(settings)
    else:
        subject_resolver = build_local_subject_resolver(settings)
    baselines_root = os.environ.get("SAC_ENTERPRISE_EVAL_BASELINES_ROOT")
    project_root = os.environ.get("SAC_ENTERPRISE_PROJECT_ROOT")
    return create_app(
        settings=settings,
        backend=backend,
        subject_resolver=subject_resolver,
        oidc_validator=oidc_validator,
        eval_baselines_root=Path(baselines_root) if baselines_root else None,
        project_root=Path(project_root) if project_root else None,
    )


def main() -> None:
    import uvicorn

    host = os.environ.get("SAC_ENTERPRISE_API_HOST", "127.0.0.1")
    port = int(os.environ.get("SAC_ENTERPRISE_API_PORT", "8080"))
    uvicorn.run(
        "safecode.enterprise.api.server:build_application",
        factory=True,
        host=host,
        port=port,
        log_level=os.environ.get("SAC_ENTERPRISE_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
