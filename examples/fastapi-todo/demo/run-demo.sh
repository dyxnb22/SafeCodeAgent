#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/sac-fastapi-todo-demo.XXXXXX")"
trap 'rm -rf "$tmp_root"' EXIT

cp -R "$repo_root/examples/fastapi-todo" "$tmp_root/fastapi-todo"
cd "$tmp_root/fastapi-todo"

PYTHONPATH="$repo_root/src" sac demo agent-loop
