#!/usr/bin/env bash
# Roll back using an immutable, separately checked-out release directory.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/compose.enterprise.yaml"
ROLLBACK_ROOT="${ENTERPRISE_ROLLBACK_ROOT:-}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for rollback" >&2
  exit 1
fi

if [[ -z "${ROLLBACK_ROOT}" || ! -f "${ROLLBACK_ROOT}/compose.enterprise.yaml" ]]; then
  echo "ENTERPRISE_ROLLBACK_ROOT must name an immutable release directory" >&2
  exit 1
fi

docker compose -f "${COMPOSE_FILE}" down
docker compose -f "${ROLLBACK_ROOT}/compose.enterprise.yaml" up -d --wait
echo "enterprise stack rolled back and restarted" >&2
