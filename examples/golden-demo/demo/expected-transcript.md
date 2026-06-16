# SafeCode Agent — Golden Demo Transcript

Full loop: bug report → context collection → diff preview → approval →
checkpoint → apply → test → commit offer → rollback evidence.

```
[setup] provider=mock network=disabled
[setup] source=examples/golden-demo
[setup] working-copy=<temp-worktree>

[task] Fix subtract() in src/calculator.py — it returns a + b instead of a - b. Run pytest to verify.

[context]
Selected files:
  src/calculator.py        (matches task keywords: subtract, calculator)
  tests/test_calculator.py (test file for target module)

[plan]
1. Read src/calculator.py to confirm the bug.
2. Read tests/test_calculator.py to understand the expected behavior.
3. Fix the return value in subtract().
4. Run pytest to verify the fix.

[reading] src/calculator.py

def subtract(a: int, b: int) -> int:
    return a + b  # BUG: should be a - b

[reading] tests/test_calculator.py

def test_subtract():
    assert subtract(10, 4) == 6  # expects 6, gets 14

[patch proposal]
--- a/src/calculator.py
+++ b/src/calculator.py
@@ -8,7 +8,7 @@
 def subtract(a: int, b: int) -> int:
-    return a + b  # BUG: should be a - b
+    return a - b

[review boundary]
Review the diff above before approving. The agent pauses here in a real run.
No file has been modified yet.

[approve]
User typed: yes
Approval recorded for this patch.

[checkpoint]
Created checkpoint: chk-20260616-subtract-fix
Backup of src/calculator.py stored at .sac/checkpoints/chk-20260616-subtract-fix/

[apply]
Patch applied to src/calculator.py in <temp-worktree>.

[audit]
Event logged: patch_applied
  file: src/calculator.py
  checkpoint: chk-20260616-subtract-fix
  sha256_before: a3f1...
  sha256_after:  9c2e...

[validation]
$ python3 -m pytest tests/ -q
3 passed in 0.04s

[commit prompt]
Suggested local commit: fix(calculator): subtract() returns a - b
No commit was created by this demo. To commit: git add src/calculator.py && git commit -m "fix(calculator): subtract() returns a - b"

[rollback evidence]
To undo at any time: sac rollback --checkpoint chk-20260616-subtract-fix
This would restore src/calculator.py from the checkpoint backup.

[cleanup]
Removed <temp-worktree>
```

## What this demonstrates

| Stage | SafeCode feature | Where to look |
|---|---|---|
| Context collection | `ContextSelector`, git-aware recency | `src/safecode/context/` |
| Patch proposal | `AgentOrchestrator.edit()` | `src/safecode/agent/orchestrator.py` |
| Diff preview | `DiffPlanner`, Rich panel | `src/safecode/agent/planner.py` |
| Human approval | `PatchApprovalGate` | `src/safecode/patch/approvals.py` |
| Checkpoint | `CheckpointManager` + sha256 | `src/safecode/checkpoint/` |
| Apply | `PatchApplier` | `src/safecode/patch/applier.py` |
| Audit log | `AuditLogger` hash-chain | `src/safecode/audit/` |
| Test run | `run_command` tool via `ShellRunner` | `src/safecode/shell/` |
| Rollback | `RollbackManager` | `src/safecode/checkpoint/rollback.py` |

All of these safety layers are active even in `--full-auto` trust mode.
The only thing that changes between trust modes is whether approval is prompted
interactively or auto-granted — the checkpoint, audit, and rollback always run.
