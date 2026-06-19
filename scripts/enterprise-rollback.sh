#!/usr/bin/env bash
# Roll back the on-prem Enterprise stack to the previous compose revision (v2.5.6).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/compose.enterprise.yaml"
ROLLBACK_TAG="${ENTERPRISE_ROLLBACK_TAG:-}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for rollback" >&2
  exit 1
fi

cd "${ROOT}"
docker compose -f "${COMPOSE_FILE}" down

if [[ -n "${ROLLBACK_TAG}" ]]; then
  git checkout "${ROLLBACK_TAG}" -- "${COMPOSE_FILE}" compose/enterprise.dev.env.example
  echo "checked out compose files from ${ROLLBACK_TAG}" >&2
fi

docker compose -f "${COMPOSE_FILE}" up -d --wait
echo "enterprise stack rolled back and restarted" >&2
