# AI Shell: First Hour

**Status: EXPERIMENTAL (v4.9)**

This tutorial shows how to use `sac shell` — SafeCode's local AI shell — to
understand a project, propose changes, run checks, and deliver work locally.

All `sac shell` surfaces are **EXPERIMENTAL** and carry no stable contract.
The shell does not auto-apply patches or auto-commit. No live provider is
required; the default `mock` provider works for all structural commands.

---

## Prerequisites

- SafeCode Agent installed (`uv sync && uv run sac doctor`)
- A project directory to work in

---

## Start the AI Shell

```bash
cd /path/to/your-project
sac shell
```

The shell opens an interactive REPL:

```
SafeCode Shell (EXPERIMENTAL v4.9)
Ask questions, use /help for slash commands, /exit to quit.
sac>
```

---

## Step 1 — Understand the Project

Ask natural-language questions:

```
sac> what is this project?
sac> /overview
```

`/overview` builds a bounded project summary from local signals:
- Detected stack (Python/TypeScript/Go/Rust)
- Git branch and recent commits
- Detected profile commands (test/lint/typecheck/build)
- Likely entrypoints and test directories
- High-signal files list
- Pinned memory files
- Current task state
- Recent failures

No network calls. No embeddings. No RAG.

---

## Step 2 — Find a Likely Bug

```
sac> /debug
```

Or ask naturally:

```
sac> what went wrong?
sac> show me the last failure
```

The shell reads redacted runtime logs and task metadata without executing any commands.

---

## Step 3 — Propose a Fix

Ask for the safest minimal change:

```
sac> make the smallest safe fix
```

This routes to `sac edit` after confirmation. The shell asks:

```
Propose edit: "make the smallest safe fix"? [y/N]:
```

If you confirm with `y`, a pending patch is proposed and the diff is shown.
The patch is **not applied yet**. No files are modified.

---

## Step 4 — Run Checks

```
sac> run the tests
```

The shell routes to the profile test suite after confirmation:

```
Run profile suite 'test'? [y/N]:
```

To run other suites:

```
sac> lint
sac> typecheck
sac> build
```

---

## Step 5 — Review and Apply the Patch

When a pending patch exists, check the diff in another terminal:

```bash
sac status
sac apply          # explicit approval: checkpoint + apply
```

Or in the shell:

```
sac> /apply
```

The shell shows a confirmation prompt before delegating to `sac apply`:

```
Apply pending patch? This will modify files. [y/N]:
```

Patches are **never applied automatically**. The `/apply` command requires
explicit confirmation.

---

## Step 6 — Rollback if Needed

If the applied patch is wrong:

```bash
sac rollback --last
```

This restores the previous checkpoint. The shell also accepts:

```
sac> /status
```

to confirm the current state before deciding.

---

## Step 7 — Commit Locally

```
sac> /commit
```

The shell asks for confirmation:

```
Commit current task locally? [y/N]:
```

This delegates to `sac commit`, which stages only files touched by the current
task. No push or remote operation occurs.

---

## Slash Command Reference

| Command    | Description |
|------------|-------------|
| `/status`  | Show current task, pending patch, and next step |
| `/task`    | Show current task details |
| `/overview`| Show bounded project structure overview |
| `/apply`   | Apply pending patch (requires confirmation) |
| `/commit`  | Commit current task locally (requires confirmation) |
| `/debug`   | Show last failure debug info |
| `/help`    | Show this help |
| `/exit`    | Exit the shell |

---

## Non-TTY / Script Mode

For scripted use, pass `--non-tty`:

```bash
echo "/overview" | sac shell --non-tty
```

Or use JSON output:

```bash
echo "what is this project?" | sac shell --non-tty --json
```

In non-TTY mode, mutation commands (`/apply`, `/commit`) print instructions
instead of executing — they never auto-apply.

---

## Session Continuity

Shell sessions are persisted under `.sac/shell/`. To resume a previous session:

```bash
sac shell --session <session-id>
```

Each session automatically binds to the current task.

---

## Safety Guarantees

- **No auto-apply**: patches are never applied without explicit `y` confirmation.
- **No auto-commit**: commits are never created without explicit `y` confirmation.
- **No auto-run**: test/lint/build suites require confirmation.
- **Audit trail**: every shell turn writes an audit event.
- **Task continuity**: shell turns are bound to the CURRENT task sidecar.
- **Rollback always available**: `sac rollback --last` recovers from any apply.

---

## What the Shell Does Not Do

The v4.9 AI shell intentionally does **not**:

- Use RAG, embeddings, or vector storage
- Connect to external services or hosted agents
- Push code or create pull requests
- Integrate with IDEs over a protocol
- Promote any new stable contract

All v4.9 surfaces are EXPERIMENTAL. See `docs/versioning-policy.md` for the
v4.9 contract position.
