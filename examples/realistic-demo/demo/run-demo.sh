#!/usr/bin/env bash
# SafeCode realistic demo — multi-file service bug to tested fix.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/sac-realistic-demo.XXXXXX")"
trap 'rm -rf "$tmp_root"' EXIT

cp -R "$repo_root/examples/realistic-demo/." "$tmp_root/"
cd "$tmp_root"

echo ""
echo "=== SafeCode Agent: Realistic Multi-file Demo ==="
echo "Project: todo service with API facade + in-memory store"
echo "Working copy: $tmp_root"
echo ""

echo "--- STEP 1: Show failing tests ---"
python3 -m pytest tests/test_todo_service.py -q --tb=short || true
echo ""

echo "--- STEP 2: SafeCode-style patch preview (mock transcript) ---"
cat <<'DIFF'
--- a/src/todo_service/store.py
+++ b/src/todo_service/store.py
@@
-        item = Todo(id=self._next_id, title=title, completed=True)
+        item = Todo(id=self._next_id, title=title, completed=False)
@@
-        return list(self._items)
+        return [item for item in self._items if not item.completed]
DIFF
echo ""
echo "[User types: yes]"
echo "[Checkpoint created]"
echo "[Patch applied]"
echo "[Audit event logged]"
echo ""

python3 - <<'PY'
from pathlib import Path

path = Path("src/todo_service/store.py")
text = path.read_text()
text = text.replace(
    "item = Todo(id=self._next_id, title=title, completed=True)",
    "item = Todo(id=self._next_id, title=title, completed=False)",
)
text = text.replace(
    "return list(self._items)",
    "return [item for item in self._items if not item.completed]",
)
path.write_text(text)
PY

echo "--- STEP 3: Run tests after fix ---"
python3 -m pytest tests/test_todo_service.py -q
echo ""
echo "--- Demo complete ---"
echo "Read the full annotated transcript:"
echo "  examples/realistic-demo/demo/expected-transcript.md"
echo ""
echo "[Rollback remains available: sac rollback --last]"
