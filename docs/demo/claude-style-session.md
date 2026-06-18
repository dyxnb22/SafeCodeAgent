# Claude-Style Session Transcript

This transcript shows the intended real-use shape of SafeCode Agent after the
unified shell work. It is provider-agnostic; with DeepSeek configured, the same
flow uses the persisted keychain credential and the selected DeepSeek model.

```text
$ sac
SafeCode 8e6b42a1 · New conversation · new · build · provider=deepseek · model=deepseek-v4-flash
/status  /sessions  /new  /memory why  /mode plan|build  /exit

sac> /status
Provider: deepseek
Credential source: keychain
Session: 8e6b42a1...
Safety policy: balanced
Next: type a request, or use /memory why to inspect injected context.

sac> Read the project and explain what is missing before release.
Reading
Searching
Completed
The project is release-ready for normal development use. The remaining work is
mostly product polish: durable cancellation, clearer approval explanation, and
keeping legacy pending patches inside the active conversation.

  Cost: 17559 in / 483 out

sac> Fix the shell so legacy pending patches belong to the current session.
Reading
Editing
Patch proposal created and waiting for approval.

diff --git a/src/safecode/shell/approvals.py b/src/safecode/shell/approvals.py
...
Approve, Reject, or Explain? [a/r/e]: e
Patch awaiting approval: legacy pending patch migrated into this conversation.

Approve, Reject, or Explain? [a/r/e]: a
Approved and applied: src/safecode/shell/approvals.py. Checkpoint: ckpt-...

sac> /tests
scripts/test-fast.sh

sac> /sessions
Recent sessions
---------------
* 8e6b42a1d91e  Fix the shell so legacy pending patches...  [active, 2 turns]

Use /resume <id>, /new, or /rename <title>.
```

## What This Demonstrates

- Bare `sac` enters the real conversation runtime.
- The session owns conversation history, agent state, memory context, and pending
  patches under `.sac/sessions/<id>/`.
- Mutating work stops at an approval boundary with a visible diff.
- `/continue`, `/approval`, and `/memory why` explain the current blocker instead
  of requiring the user to understand internal state files.
- Re-entering `sac` resumes the latest conversation and shows the last response.
