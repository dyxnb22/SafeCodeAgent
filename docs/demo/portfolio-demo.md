# SafeCode Agent Portfolio Demo

**The fastest way to understand what SafeCode Agent does**: a complete loop
from bug report to verified local fix, showing every safety gate.

## Scenario

**Project:** a Python calculator library with a deliberate bug.

```python
# src/calculator.py — the bug
def subtract(a: int, b: int) -> int:
    return a + b  # BUG: should be a - b
```

**Test that fails:**

```python
# tests/test_calculator.py
def test_subtract():
    assert subtract(10, 4) == 6  # gets 14, not 6
```

**Goal given to the agent:**
> Fix subtract() in src/calculator.py — it returns a + b instead of a - b.
> Run pytest to verify.

## How to run

**Mock mode (no API key required):**

```bash
git clone <repo> && cd SafeCodeAgent
uv sync
examples/golden-demo/demo/run-demo.sh
```

**With a real provider (optional):**

```bash
sac setup --provider anthropic   # or openai, deepseek
cd examples/golden-demo
sac shell
# type: Fix subtract() in src/calculator.py — it returns a + b instead of a - b.
```

## What the agent does, step by step

| Step | What happens | Safety gate |
|---|---|---|
| 1. Context | Reads `src/calculator.py` and `tests/test_calculator.py` | Read-only, redacted |
| 2. Plan | Identifies the wrong operator on line 8 | No write yet |
| 3. Diff | Proposes `-    return a + b` → `+    return a - b` | Shown to user |
| 4. Approve | Waits for `yes` before touching any file | Hard gate — no bypass |
| 5. Checkpoint | Backs up `src/calculator.py` with SHA-256 | Always runs |
| 6. Apply | Writes the fix to the file | Only after approval + checkpoint |
| 7. Audit | Appends a hash-linked event to `.sac/audit.jsonl` | Always runs |
| 8. Test | Runs `pytest tests/ -q` | Policy-gated command |
| 9. Result | Reports 3 passed | No auto-commit |
| 10. Rollback | Available at any time via `sac rollback --last` | Always available |

## Reading the transcript

The full recorded output is at
[examples/golden-demo/demo/expected-transcript.md](../../examples/golden-demo/demo/expected-transcript.md).

Key annotations:
- `[review boundary]` — where the agent stops and waits for approval.
- `[checkpoint]` — backup created before any write.
- `[audit]` — append-only event with before/after SHA-256.
- `[rollback evidence]` — how to undo if the fix were wrong.

## Architecture notes for interviewers

SafeCode Agent's safety model is not bolted on — it is the core loop:

```text
collect context
→ propose patch
→ preview diff          ← user sees this
→ human approval        ← hard stop; agent cannot bypass
→ checkpoint + SHA-256  ← always
→ apply patch
→ audit log (hash chain)← always
→ rollback available    ← always
```

This structure means:
- The agent can never write files without approval.
- Every write is reversible.
- Every write is auditable.
- In `--full-auto` mode, approval is auto-granted, but checkpoint + audit +
  rollback still run on every write.

The same safety loop applies to shell commands (`run_command`), MCP write
tools, and GitHub operations — all go through `ToolCallGate` before execution.

## Key source files

- `src/safecode/agent/orchestrator.py` — `AgentOrchestrator.edit()`: the entry point
- `src/safecode/agent/loop.py` — `AgentLoop`: the plan/step/tool-call loop
- `src/safecode/patch/` — parse, validate, diff, apply
- `src/safecode/checkpoint/` — backup and rollback
- `src/safecode/audit/logger.py` — append-only SHA-256 hash-chain log
- `src/safecode/agent/prompts.py` — `SYSTEM_PROMPT`: what the model is told
- `src/safecode/tools/gate.py` — `ToolCallGate`: universal pre-flight gate
