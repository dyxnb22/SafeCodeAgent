#!/usr/bin/env bash
# SafeCode Agent golden demo — from bug report to tested commit (mock mode).
# No live provider credentials required.
#
# What this shows:
#   1. The broken project starts with a failing test.
#   2. The agent proposes a diff (shown from expected-transcript.md).
#   3. The fix is applied and the tests pass.
#
# Usage: examples/golden-demo/demo/run-demo.sh

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
demo_src="$repo_root/examples/golden-demo"
tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/sac-golden-demo.XXXXXX")"
trap 'rm -rf "$tmp_root"' EXIT

# Copy the demo project to a temp directory so we never mutate the source.
cp -R "$demo_src/src" "$tmp_root/src"
cp -R "$demo_src/tests" "$tmp_root/tests"

echo ""
echo "=== SafeCode Agent: Golden Demo ==="
echo "Project: broken calculator — subtract() returns a + b instead of a - b"
echo "Working copy: $tmp_root"
echo ""

echo "--- STEP 1: Show the failing test (before fix) ---"
python3 -m pytest "$tmp_root/tests/test_calculator.py::test_subtract" \
    --tb=short -q 2>&1 | head -20 || true
echo ""

echo "--- STEP 2: Agent proposes and applies patch (mock mode) ---"
echo "   SafeCode would show this diff:"
echo ""
echo "   --- a/src/calculator.py"
echo "   +++ b/src/calculator.py"
echo "   @@ -8,4 +8,4 @@ def add(a, b):"
echo "    def subtract(a: int, b: int) -> int:"
echo "   -    return a + b  # BUG: should be a - b"
echo "   +    return a - b"
echo ""
echo "   [User types: yes]"
echo "   [Checkpoint created]"
echo "   [Patch applied]"
echo "   [Audit event logged]"
echo ""

# Apply the fix in the temp copy (simulating what the agent would do after approval).
python3 -c "
import sys
from pathlib import Path
src = Path('$tmp_root/src/calculator.py')
text = src.read_text()
fixed = text.replace('return a + b  # BUG: should be a - b', 'return a - b')
if fixed == text:
    print('ERROR: fix pattern not found in source', file=sys.stderr)
    sys.exit(1)
src.write_text(fixed)
"

echo "--- STEP 3: Run pytest — all tests should pass ---"
python3 -m pytest "$tmp_root/tests/" -q 2>&1
echo ""

echo "--- Demo complete ---"
echo "Read the full annotated transcript:"
echo "  examples/golden-demo/demo/expected-transcript.md"
echo ""
echo "See docs/demo/portfolio-demo.md for the full scenario and architecture notes."
echo ""
echo "[In a real sac session the agent would also offer: git add + git commit]"
echo "[Rollback is always available: sac rollback --last]"
