#!/usr/bin/env bash
# Bring up the disposable Enterprise dev stack for learning and interviews.
#
# Unlike scripts/enterprise-up.sh, this profile accepts the committed example
# credentials and prepares local OIDC material for console login.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/compose.enterprise.yaml"
ENV_FILE="${ROOT}/compose/enterprise.dev.env"
ENV_EXAMPLE="${ROOT}/compose/enterprise.dev.env.example"
TOKEN_SCRIPT="${ROOT}/scripts/issue-dev-token.py"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for the enterprise development profile" >&2
  exit 1
fi

if [[ ! -f "${ENV_EXAMPLE}" ]]; then
  echo "missing compose env example: ${ENV_EXAMPLE}" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  echo "created ${ENV_FILE} from example (development credentials)" >&2
fi

if ! python3 -c "import jwt" >/dev/null 2>&1; then
  echo "installing PyJWT for local dev token issuance..." >&2
  python3 -m pip install -q "PyJWT[crypto]>=2.8.0"
fi

python3 "${TOKEN_SCRIPT}" --prepare

cd "${ROOT}"
docker compose -f "${COMPOSE_FILE}" config >/dev/null
echo "starting enterprise dev stack (first boot may take a few minutes)..." >&2
docker compose -f "${COMPOSE_FILE}" up -d --wait

API_URL="http://127.0.0.1:8080"
CONSOLE_URL="http://127.0.0.1:3000"

if command -v curl >/dev/null 2>&1; then
  curl -sf "${API_URL}/healthz" >/dev/null
fi

cat <<EOF

Enterprise dev stack is up.

  API:     ${API_URL}
  Console: ${CONSOLE_URL}
  Tenant:  tenant-dev

Paste this bearer token on the console login page (development only):

$(python3 "${TOKEN_SCRIPT}")

Stop and remove containers:

  docker compose -f compose.enterprise.yaml down -v

For production-like startup with non-development credentials, use scripts/enterprise-up.sh instead.
EOF
