# SafeCode Command Reference

This page collects command details that are useful after the first run. For the
short guided path, start with [../user-guide.md](../user-guide.md).

## Core Daily Commands

The default `sac --help` intentionally shows the small daily command surface.
Advanced and experimental commands remain callable; run `sac help --all` to see
the full hidden surface.

```bash
sac quickstart
sac setup --wizard
sac doctor
sac ask "What is this project?"
sac edit "Make the smallest safe change"
sac apply
sac rollback --last
sac history
sac version
```

`sac edit` proposes a pending patch and diff. `sac apply` is the explicit
approval step: it validates again, creates a checkpoint, applies, and writes
audit events. `sac rollback --last` restores the most recent apply checkpoint.

## AI Shell (v4.9, EXPERIMENTAL)

```bash
cd myproject && sac shell
```

The shell routes natural-language input to existing SafeCode primitives:
read-only overview/debug, approval-gated edit/run/apply/commit, and exit. No
mutation path auto-applies or auto-commits. No RAG or embeddings.

## Task-First Flow (v4.x, EXPERIMENTAL)

```bash
sac task new "Fix auth regression"
sac profile detect
sac status
sac ask "explain the auth flow"
sac edit "Fix auth regression"
sac fix --watch
sac apply
sac rollback --last
sac commit --message-from-task
sac resume
sac debug last-failure
sac debug bundle --out debug.tgz
```

Task commands group edits, applies, rollbacks, fix runs, and local delivery
under a named task. If no task is active when you run `sac edit`, SafeCode can
auto-create one so the workflow stays unblocked.

## Resume and Budgets (v4.4, EXPERIMENTAL)

```bash
sac resume
sac resume <task-id>
sac resume --json
sac resume --continue-agent
sac status
sac task budget show
sac task budget set --steps 8 --time-seconds 600 --retries 2 --tokens 60000
sac task budget show --json
```

`sac resume` is passive: it sets the task as CURRENT, prints a redacted summary
and next safe step, and never runs `edit`, `fix`, `apply`, or a shell command.
`--continue-agent` reconstructs existing agent state and re-enters the agent
loop, but still never automatically re-runs `apply`, `commit`, `rollback`,
validation, or repair.

Budgets are stored separately from the task sidecar. Budget breaches record
experimental `failure_category: budget_exceeded`. Budgets do not weaken command
policy, approval, sandbox, or network gates.

## Local Git Delivery (v4.5, EXPERIMENTAL)

```bash
sac diff --task
sac diff --task --json
sac commit --message-from-task
sac commit --include-task-summary
sac commit --json
sac branch new follow-up/auth-cleanup
sac branch new follow-up/auth-cleanup --json
```

`sac commit` stages only files SafeCode can associate with the CURRENT task
through applied patch, checkpoint, audit, or sidecar metadata. If that file set
cannot be determined, commit fails closed. The dirty-tree guard protects
`sac apply` and `sac commit`; unrelated tracked or staged changes are refused
by default.

Rollback after a committed apply is conservative. If `sac rollback --last`
detects that the latest apply appears committed, it refuses and prints a
`git revert <sha>` hint. `--force-uncommit` is the explicit dangerous opt-in.

## Project Memory (v4.6, EXPERIMENTAL)

New memory writes use:

```text
.sac/memory/project.md
.sac/memory/recent-failures.jsonl
.sac/memory/recent-edits.jsonl
.sac/memory/pinned-files.txt
.sac/tasks/<task_id>/memory.md
```

```bash
sac memory show
sac memory add-note "health route must stay synchronous"
sac memory add-note "parser edge case" --task-id <task-id>
sac memory show --task --task-id <task-id>
sac memory show --recent-failures
sac memory show --recent-edits
sac memory pin src/app.py
sac memory show --pinned
sac memory unpin src/app.py
sac memory clear --recent-failures --yes
```

Pinned files still pass through the same ignore, sensitive-file, binary,
redaction, and project-root checks as ordinary context. Recent failures are
redacted and bounded before being reused as task context.

## Debug and Audit (v4.7, EXPERIMENTAL)

```bash
sac debug last-failure
sac debug last-failure --task <task-id> --json
sac debug bundle --out safecode-debug.tar.gz
sac debug bundle --task <task-id> --out safecode-debug.tar.gz --force
sac debug bundle --out safecode-debug.tar.gz --json
sac audit query --task <task-id>
sac audit query --type shell_blocked --limit 20
sac audit query --since 2026-01-01 --json
```

Debug commands are local and redacted. `sac debug bundle` writes SafeCode
metadata only: manifest, version/config snapshot, doctor-equivalent data,
runtime logs, verified audit events, selected task sidecars, project profile,
and memory metadata. It excludes project source code.

## Project Command Profile (v4.2, EXPERIMENTAL)

```bash
sac profile detect
sac profile show
sac profile show --json
sac profile set test "pytest -q --tb=short"
sac profile set lint "ruff check src/"
sac profile clear test
sac run --suite test
sac run --suite lint
sac run --suite typecheck
sac run --suite build
```

SafeCode detects commands for Python, Node.js, Go, and Rust. Missing tools are
reported as SKIP by `sac doctor`, not FAIL. `sac fix` uses the profile test
command unless `--test-command` is provided.

## Fix Watch (v4.3, EXPERIMENTAL)

```bash
sac fix
sac fix --test-command "pytest tests/test_foo.py -q"
sac fix --test-command "go test ./..."
sac fix --json
sac fix --watch
sac fix --watch --max-iterations 5
sac fix --watch --timeout-seconds 60
sac fix --watch --rerun-suite test
sac fix --watch --rerun-suite all
```

`sac fix --watch` runs one bounded test-fix loop step per invocation. It never
applies patches automatically. Review the pending diff, run `sac apply`, then
run `sac fix --watch` again.

## Machine-Readable Output

Many commands support `--json`:

```bash
sac ask "question" --json
sac edit "task" --json
sac apply --json
sac fix --json
sac fix --watch --json
sac resume --json
sac task budget show --json
sac commit --json
sac branch new my-branch --json
sac diff --task --json
sac memory show --json
sac memory pin src/app.py --json
sac debug last-failure --json
sac debug bundle --out safecode-debug.tar.gz --json
sac audit query --task <task-id> --json
```

The JSON envelope is a stable contract documented in
[../public-contracts.md](../public-contracts.md).

## Agent Journal (v4.11.1+, EXPERIMENTAL)

Agent sessions record append-only journal files at:

```text
.sac/agent_journals/<session_id>.jsonl
```

```bash
sac agent journal
sac status --json
```

Since v4.11.1, journals include `typed_step` and `typed_result` events
alongside legacy events. Corrupt or future-version lines are skipped
independently, and missing/empty journal helpers return `None`.
