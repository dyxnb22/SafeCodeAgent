#!/usr/bin/env bash
# Minimal deterministic backup for the local Enterprise artifact tree (v2.5.4).
set -euo pipefail

SAC_ROOT="${1:-}"
OUTPUT="${2:-}"

if [[ -z "${SAC_ROOT}" || -z "${OUTPUT}" ]]; then
  echo "usage: enterprise-backup.sh SAC_ROOT OUTPUT.tar.gz" >&2
  exit 1
fi

if [[ ! -d "${SAC_ROOT}" ]]; then
  echo "artifact root does not exist: ${SAC_ROOT}" >&2
  exit 1
fi

if [[ "$(basename "${SAC_ROOT}")" == ".sac" ]]; then
  PROJECT_ROOT="$(dirname "${SAC_ROOT}")"
  PARENT="$(dirname "${PROJECT_ROOT}")"
  ITEMS=("$(basename "${PROJECT_ROOT}")")
  if [[ -n "${SAFECODE_AUDIT_ANCHOR_DIR:-}" ]]; then
    ANCHOR_PATH="$(cd "${SAFECODE_AUDIT_ANCHOR_DIR}" && pwd)"
    case "${ANCHOR_PATH}" in
      "${PARENT}"/*)
        ANCHOR_BASE="$(basename "${ANCHOR_PATH}")"
        if [[ "${ANCHOR_BASE}" != "$(basename "${PROJECT_ROOT}")" ]]; then
          ITEMS+=("${ANCHOR_BASE}")
        fi
        ;;
    esac
  fi
  mkdir -p "$(dirname "${OUTPUT}")"
  tar -czf "${OUTPUT}" -C "${PARENT}" "${ITEMS[@]}"
else
  BACKUP_DIR="${SAC_ROOT}"
  mkdir -p "$(dirname "${OUTPUT}")"
  tar -czf "${OUTPUT}" -C "$(dirname "${BACKUP_DIR}")" "$(basename "${BACKUP_DIR}")"
fi
echo "backup written to ${OUTPUT}" >&2
