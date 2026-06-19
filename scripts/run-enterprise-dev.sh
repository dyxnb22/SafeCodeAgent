#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/compose.enterprise.yaml"
ENV_FILE="${ROOT}/compose/enterprise.dev.env"
ENV_EXAMPLE="${ROOT}/compose/enterprise.dev.env.example"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for the enterprise development profile" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  echo "created ${ENV_FILE} from example; edit credentials locally if needed" >&2
fi

cd "${ROOT}"
docker compose -f "${COMPOSE_FILE}" config >/dev/null
docker compose -f "${COMPOSE_FILE}" up -d --wait

echo "Team Server dev profile is up on http://127.0.0.1:8080" >&2
echo "Issue a dev bearer token with: uv run python scripts/issue-dev-token.py" >&2
