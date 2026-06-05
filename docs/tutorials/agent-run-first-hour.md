# Agent Run — First Hour (EXPERIMENTAL)

> **EXPERIMENTAL**: All surfaces documented here are experimental and carry
> no stable contract. Behavior may change in future releases.

This tutorial walks through your first `sac agent run` session: from
setting a goal to reviewing a proposed patch — without leaving the terminal.

## Prerequisites

- SafeCode Agent installed (`uv sync && uv run sac --help`)
- A project directory with a working test suite
- A provider configured (`sac setup --wizard`, pick `deepseek` or `openai`)
- Doctor confirms your setup (`sac doctor`)

## Step 1: Pick a task

Create a task for the agent to work on:

```bash
cd myproject
sac task new "add input validation to the user registration endpoint"
```

## Step 2: Run the agent

```bash
sac agent run "add input validation to the user registration endpoint"
```

The agent will:
1. Plan steps toward the goal.
2. Collect context (files, test results, pinned memory).
3. Propose a patch and stop for your approval.

No files are modified until you explicitly approve.

## Step 3: Review the proposed patch

When the agent stops with `approval_required`, it prints a pending patch path:

```
Patch proposal saved — no files modified yet.
File  : .sac/pending_patch.json
ID    : patch-abc123

Next steps:
  sac apply          — preview diff and apply
  sac apply --preview — preview diff only
```

Review the diff:

```bash
sac apply --preview
```

## Step 4: Apply and verify

```bash
sac apply          # applies the patch
sac run --suite test  # runs your test suite through policy checks
```

## Options

| Flag | Default | Purpose |
|---|---|---|
| `--max-steps N` | 8 | Maximum agent steps before stopping |
| `--auto-approve-read-only` | off | Auto-approve read-only context steps only (never edit/apply/run) |
| `--no-validate` | off | Skip validation loop (logs a warning) |
| `--json` | off | Machine-readable output |

## Shell agentic mode

`sac shell --agentic` drives the same `AgentLoop.run()` path as `sac agent run`
but reads the goal interactively from the shell prompt:

```bash
sac shell --agentic
# > add a DELETE /todos/{id} endpoint with a passing test
```

Without `--agentic`, the shell uses the existing v4.9 intent router.

## Safety notes

- `--auto-approve-read-only` **never** approves `edit`, `apply`, `run`, `fix`,
  `commit`, or `rollback` steps — those always require interactive approval.
- In non-TTY mode, approval-required steps fail closed if they require mutation.
- No files are modified without your explicit `sac apply` approval.
- No commits are created without your explicit `sac commit` approval.

## What's next?

- `docs/tutorials/from-task-to-tested-commit.md` (coming in v4.12)
- `examples/fastapi-todo/` — a runnable end-to-end demo (coming in v4.12)
