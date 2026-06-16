#!/usr/bin/env bash
set -euo pipefail

PYTHONPATH="${PYTHONPATH:-src}" python3 -m pytest -q -m "not slow" "$@"
