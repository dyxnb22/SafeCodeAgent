#!/usr/bin/env bash
# SafeCode Agent golden demo — from bug report to tested commit.
# Runs in mock mode: no live provider credentials required.
#
# Usage: examples/golden-demo/demo/run-demo.sh

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/sac-golden-demo.XXXXXX")"
trap 'rm -rf "$tmp_root"' EXIT

cp -R "$repo_root/examples/golden-demo" "$tmp_root/golden-demo"
cd "$tmp_root/golden-demo"

echo ""
echo "=== SafeCode Agent: Golden Demo ==="
echo "Project: broken calculator (subtract returns a + b instead of a - b)"
echo "Goal: fix the bug and verify with pytest"
echo ""

# Show the failing test
echo "--- Failing test (before fix) ---"
python3 -m pytest tests/test_calculator.py::test_subtract -q 2>&1 | head -15 || true
echo ""

echo "--- Running SafeCode Agent (mock mode) ---"
PYTHONPATH="$repo_root/src" python3 -m safecode.cli demo agent-loop \
    --project-root "$tmp_root/golden-demo" \
    --goal "Fix subtract() in src/calculator.py — it returns a + b instead of a - b. Run pytest to verify." \
    2>&1 || true

echo ""
echo "=== Demo complete. See examples/golden-demo/demo/expected-transcript.md for the recorded output. ==="
