"""Worker process entrypoint for the Team Server (v2.1.7-T2)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from safecode.enterprise.api.dependencies import build_backend
from safecode.enterprise.api.settings import load_team_server_settings_from_env
from safecode.enterprise.worker.runner import WorkerRunner


def main() -> None:
    settings = load_team_server_settings_from_env()
    artifacts_root = Path(
        os.environ.get("SAC_ENTERPRISE_ARTIFACTS_ROOT", "/var/lib/safecode")
    )
    backend = build_backend(settings, sac_root=artifacts_root)
    worker_id = os.environ.get("SAC_ENTERPRISE_WORKER_ID", "worker-1")
    project_root = Path(os.environ.get("SAC_ENTERPRISE_PROJECT_ROOT", artifacts_root.parent))
    poll_seconds = float(os.environ.get("SAC_ENTERPRISE_WORKER_POLL_SECONDS", "1.0"))
    runner = WorkerRunner(backend, worker_id=worker_id, project_root=project_root)
    while True:
        processed = runner.process_once()
        runner.heartbeat_active_leases()
        if not processed:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
