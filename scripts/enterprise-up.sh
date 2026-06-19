#!/usr/bin/env bash
# Bring up the on-prem Enterprise stack (v2.5.6).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/compose.enterprise.yaml"
ENV_FILE="${ROOT}/compose/enterprise.dev.env"
ENV_EXAMPLE="${ROOT}/compose/enterprise.dev.env.example"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for the enterprise deployment profile" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "production env file is required: ${ENV_FILE}" >&2
  echo "start from ${ENV_EXAMPLE}, replace every development credential, then retry" >&2
  exit 1
fi


if grep -Eq 'issuer\.example|safecode_dev|POSTGRES_PASSWORD=safecode_dev' "${ENV_FILE}"; then
  echo "refusing development credentials in production-like startup" >&2
  exit 1
fi

cd "${ROOT}"
docker compose -f "${COMPOSE_FILE}" config >/dev/null
docker compose -f "${COMPOSE_FILE}" up -d --wait
echo "enterprise stack is up" >&2
