#!/usr/bin/env bash
# Restore a local Enterprise artifact tree from backup (v2.5.4).
set -euo pipefail

ARCHIVE="${1:-}"
DEST_ROOT="${2:-}"

if [[ -z "${ARCHIVE}" || -z "${DEST_ROOT}" ]]; then
  echo "usage: enterprise-restore.sh ARCHIVE.tar.gz DEST_PARENT_DIR" >&2
  exit 1
fi

if [[ ! -f "${ARCHIVE}" ]]; then
  echo "archive does not exist: ${ARCHIVE}" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/validate-enterprise-backup.py" "${ARCHIVE}" "${DEST_ROOT}"
echo "restored into ${DEST_ROOT}" >&2
