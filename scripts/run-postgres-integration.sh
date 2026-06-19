#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/compose/postgres-integration.yaml"
DEFAULT_DSN="postgresql://safecode:safecode_test@127.0.0.1:5432/safecode_enterprise_test"
export SAC_ENTERPRISE_TEST_DATABASE_URL="${SAC_ENTERPRISE_TEST_DATABASE_URL:-$DEFAULT_DSN}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for the postgres integration lane" >&2
  exit 1
fi

cd "${ROOT}"
docker compose -f "${COMPOSE_FILE}" up -d --wait

cleanup() {
  docker compose -f "${COMPOSE_FILE}" down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

uv run pytest tests/enterprise/persistence/postgres -m postgres_integration -q "$@"
