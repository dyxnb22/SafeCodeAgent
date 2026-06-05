# SafeCode MVP User Guide

This guide covers the v4.12.x path for a new user: install SafeCode, run the
mock demo, set up a provider when needed, run a coding task, fix a failing
test, and review/apply proposed patches safely.

Start with the resume-MVP walkthrough:

- [From Task to Tested Commit](tutorials/from-task-to-tested-commit.md)
- [FastAPI todo example](../examples/fastapi-todo/)
- [Recorded demo transcript](../examples/fastapi-todo/demo/expected-transcript.md)

## AI Shell (v4.9, EXPERIMENTAL)

v4.9 adds `sac shell` — an interactive local AI shell. Start with:

```bash
cd myproject && sac shell
```

The shell accepts natural-language questions and routes them to existing
SafeCode primitives. All mutation paths require explicit confirmation:

```
sac> what is this project?      — read-only overview
sac> /overview                  — structured project context
sac> /debug                     — last failure summary
sac> make the smallest safe fix — proposes patch after confirmation
sac> run the tests              — runs profile test suite after confirmation
sac> /apply                     — apply pending patch after confirmation
sac> /commit                    — local commit after confirmation
sac> /exit
```

**No auto-apply. No auto-commit. No RAG or embeddings. All surfaces EXPERIMENTAL.**

See [docs/tutorials/ai-shell-first-hour.md](tutorials/ai-shell-first-hour.md) for the full tutorial.

## Task-First Daily Loop (v4.x, EXPERIMENTAL)

The v4.x daily loop links task creation, context detection, editing, testing,
local delivery, memory, and debug into one session. All steps below are
EXPERIMENTAL. No step auto-applies or auto-commits. No live provider is required
(the default `mock` provider works for all structural commands).

```bash
sac quickstart                       # detect stack, show demo, print next steps
sac task new "Fix auth regression"   # create task, set CURRENT
sac profile detect                   # detect test/lint/typecheck/build commands
sac status                           # check CURRENT task state and next step
sac ask "explain the auth flow"      # read-only question, no patch proposed
sac edit "Fix auth regression"       # propose patch → preview diff → await approval
# — or use the approval-gated test-fix loop —
sac fix --watch                      # run tests, propose repair patch on failure
sac apply                            # explicit approval: checkpoint + apply patch
sac rollback --last                  # undo last apply if the patch is wrong
sac commit --message-from-task       # local commit: CURRENT task files only, no push
sac resume                           # recover an open/interrupted task, print next step
sac debug last-failure               # summarize last redacted failure, never executes
sac debug bundle --out debug.tgz     # redacted metadata bundle, no source code
```

Recovery after interruption:
```bash
# Ctrl-C during sac edit/fix/run marks the task interrupted and prints:
#   resume with: sac resume
sac resume           # passive: sets CURRENT, prints redacted summary and next step
sac status           # confirm task state before continuing
```

## Task-First Flow (v4.1, EXPERIMENTAL)

v4.1 adds an optional task layer that groups edits, applies, rollbacks, and
fix runs under a named task with a sidecar journal. All task commands are
**EXPERIMENTAL** and their interface may change in v4.2+.

```bash
# Start a named task (creates .sac/tasks/<id>.json and sets CURRENT)
sac task new "Fix calculator add function"

# Subsequent sac edit / apply / rollback / fix / run calls attach to CURRENT
sac edit "Fix the add function"
sac apply

# Check current task and next recommended step
sac status

# Show all tasks
sac task list

# Show events for a specific task (EXPERIMENTAL)
sac history --task <task-id>

# Close the task when done
sac task close
```

If no task is active when you run `sac edit` (or another wiring command),
SafeCode auto-creates one so the workflow stays unblocked.

## Resume And Recovery (v4.4, EXPERIMENTAL)

If you press Ctrl-C during `sac edit`, `sac fix`, `sac fix --watch`, or
`sac run`, SafeCode marks the current task `interrupted`, appends an
interruption marker, and exits 130.

```bash
sac resume
sac status
```

`sac resume` is passive: it sets the task as CURRENT, prints a redacted summary
and next safe step, and never runs `edit`, `fix`, `apply`, or a shell command.
To resume a specific task:

```bash
sac resume <task-id>
```

For agentic sessions, `sac resume` also reads the existing
`.sac/agent_journals/<session_id>.jsonl` journal when one is associated with
the current task or current agent session. The summary includes the last plan,
last typed step result, and a suggested next safe step such as continuing the
agent run or applying a pending patch.

```bash
sac resume --json
sac resume --continue-agent
```

`--continue-agent` reconstructs the existing `AgentLoop` state and then re-enters
`AgentLoop.run()`. It is still approval-gated and never automatically re-runs
`apply`, `commit`, `rollback`, validation, or repair.

Closed tasks are refused. Start a new task when the old one is closed:

```bash
sac task new "Continue the recovery work"
```

## Task Budgets (v4.4, EXPERIMENTAL)

Per-task budgets are stored separately from the task sidecar and are
experimental. Defaults are 8 steps, 600 seconds, 2 retries, and 60000 tokens.

```bash
sac task budget show
sac task budget set --steps 8 --time-seconds 600 --retries 2 --tokens 60000
sac task budget show --json
```

Budget breaches record experimental `failure_category: budget_exceeded` with
the tripped budget. Budgets do not weaken command policy, approval, sandbox, or
network gates.

`AgentLoop` also has an experimental stuck-loop guard. Three identical
consecutive tool intents for a task abort with `failure_category: loop_stuck`.
This is separate from the v4.3 `loop_no_progress` fix-watch guard and is not a
stable runtime taxonomy.

## Local Git Delivery (v4.5, EXPERIMENTAL)

After a task has produced and applied a patch, the local delivery flow is:

```bash
sac task new "Fix auth regression"
sac edit "Fix auth regression"
sac apply
sac diff --task
sac commit --message-from-task
sac branch new follow-up/auth-cleanup
```

`sac commit` is task-aware: it stages only files SafeCode can associate with
the CURRENT task through applied patch, checkpoint, audit, or sidecar metadata.
If that file set cannot be determined, commit fails closed instead of staging
the whole worktree. `sac diff --task [<task-id>]` is read-only and shows
applied plus pending task changes where available.

The dirty-tree guard protects `sac apply` and `sac commit`. Unrelated tracked
or staged changes are refused by default; untracked files outside touched
directories are ignored; untracked files inside touched directories are
blocked. Use `--allow-unrelated-changes` only after manual inspection.

Rollback after a committed apply is conservative. If `sac rollback --last`
detects that the latest apply appears committed, it refuses and prints a
`git revert <sha>` hint. The default path never rewrites git history.
`--force-uncommit` is the explicit dangerous opt-in and records an audit event.

## Project Memory (v4.6, EXPERIMENTAL)

Project memory is a unified experimental view over project notes, task notes,
pinned files, and bounded recent failures. New writes use the v4.6 layout:

```text
.sac/memory/project.md
.sac/memory/recent-failures.jsonl
.sac/memory/recent-edits.jsonl
.sac/memory/pinned-files.txt
.sac/tasks/<task_id>/memory.md
```

Legacy `.sac/memory.json`, `.sac/progress.md`, and `SAC.md` remain readable,
but new memory writes go to the v4.6 layout.

```bash
sac memory show
sac memory add-note "health route must stay synchronous"
sac memory add-note "parser edge case" --task-id <task-id>
sac memory show --task --task-id <task-id>
sac memory pin src/app.py
sac memory show --pinned
sac memory unpin src/app.py
sac memory clear --recent-failures --yes
```

Pinned files are considered during context selection, but they consume a
bounded pinned-files quota and do not replace task-relevant keyword context
entirely. Missing pinned files are reported as `pinned_missing` metadata.
Pinned files still pass through the same ignore, sensitive-file, binary,
redaction, and project-root checks as ordinary context.

When `sac fix` or `sac fix --watch` observes a failing command, SafeCode stores
a bounded redacted recent-failure entry. Later `sac fix` prompts include the
newest three recent failures as task context, which can help repeated failures
without exposing raw secret-bearing output.

## Debug Workflow (v4.7, EXPERIMENTAL)

When a run fails, start with the newest redacted failure summary:

```bash
sac debug last-failure
sac debug last-failure --task <task-id> --json
```

The summary is read-only. It inspects SafeCode runtime logs, task sidecars,
recent-failure memory, and audit events, then reports the experimental
failure category, message, source, task id, command/file when known, and the
suggested next command from the failure taxonomy table.

To share local diagnostic context without project source code:

```bash
sac debug bundle --out safecode-debug.tar.gz
sac debug bundle --task <task-id> --out safecode-debug.tar.gz --force
```

The bundle contains redacted SafeCode metadata only: manifest, version/config
snapshot, doctor-equivalent data, runtime logs, verified audit events, selected
task sidecars, project profile, and memory metadata. It excludes project source
code, refuses overwrite unless `--force` is passed, and is capped at 5 MiB.

For audit history, query verified events by task, type, or date:

```bash
sac audit query --task <task-id>
sac audit query --type shell_blocked --limit 20
sac audit query --since 2026-01-01 --json
```

`sac audit query` verifies audit integrity before returning events and never
writes audit entries.

## Quickstart (fastest path)

After installing, run the single guided entry point:

```bash
sac quickstart
```

This will:
1. Detect or create `.sac/config.toml` with safe defaults (mock provider, balanced policy).
2. Detect your project stack (Python/TypeScript/Go/Rust) and adapt next-step hints.
3. Display the current provider and policy.
4. Recommend the `cli-version-flag` demo workflow.
5. Print stack-appropriate next commands to run.

To also materialise the demo project locally:

```bash
sac quickstart --demo
```

### Interactive setup wizard

For first-time provider configuration, use the interactive wizard:

```bash
sac setup --wizard
```

In a TTY, the wizard walks you through provider, model, and policy selection.
In CI/non-TTY mode, it prints a static configuration template and exits 0 without prompting.

Safety invariants: the wizard cannot write a config that lowers your current user-level
safety policy. Switching from `mock` to a live provider requires explicit confirmation.
Enabling network access requires two confirmations.

#### DeepSeek wizard walkthrough (v4.10.1, EXPERIMENTAL)

To configure the DeepSeek provider interactively:

```bash
export DEEPSEEK_API_KEY=sk-...   # set before running sac; never written to disk
sac setup --wizard
```

At the provider prompt, choose `deepseek`. The wizard will:

1. Confirm that you want to switch away from mock (requires your approval).
2. Remind you to set `DEEPSEEK_API_KEY` in the environment — it will **not** prompt for
   the key value and will **never** write it to disk.
3. Prompt for a model name (default: `deepseek-v4-pro`).
4. Proceed through policy and network prompts as normal.

The resulting `.sac/config.toml` will contain:

```toml
[llm]
provider = "deepseek"
model = "deepseek-v4-pro"
# base_url is resolved automatically from the DeepSeek preset
```

After setup, run `sac doctor` to verify the API key is visible and the static
network-policy verdict is acceptable before making live calls.

## Fixing failing tests with sac fix

`sac fix` automates the test-detect → run → redact → propose cycle:

```bash
sac fix
```

This will:
1. Auto-detect the test command (`pytest`, `go test ./...`, `npm test`, etc.).
2. Run it and capture the failure output.
3. Redact any secrets from the output.
4. Invoke `sac edit` with the failure context to propose a repair patch.
5. Leave the patch pending for your review.

Then:
```bash
sac apply    # after reviewing the diff
# or
sac rollback --last   # if you change your mind
```

To override the test command:

```bash
sac fix --test-command "pytest tests/test_foo.py -q"
sac fix --test-command "go test ./..."
sac fix --json   # machine-readable output
```

If tests are already passing, `sac fix` reports success without proposing a patch.

### Approval-gated watch loop (v4.3, EXPERIMENTAL)

`sac fix --watch` runs one bounded test-fix loop step per invocation. It never
applies patches automatically.

```bash
sac fix --watch
# review the pending diff
sac apply
sac fix --watch
```

On failure, watch mode records a task fix-loop iteration and leaves a pending
patch for review. After you explicitly run `sac apply`, the next
`sac fix --watch` reruns the selected test or suite. If it passes, the task
loop state is marked passing/applied. If it still fails, SafeCode may propose a
follow-up pending patch, still requiring another explicit `sac apply`.

Useful controls:

```bash
sac fix --watch --max-iterations 5
sac fix --watch --timeout-seconds 60
sac fix --watch --rerun-suite test
sac fix --watch --rerun-suite all
```

`--rerun-suite all` uses the project profile in deterministic order:
`test`, `lint`, `typecheck`, `build`. Missing profile suites are skipped with a
clear note; blocked suite commands stop safely through the existing command
policy path.

## Machine-readable output

Most commands support `--json` for scripting:

```bash
sac fix --json
sac edit "task" --json
sac ask "question" --json
sac apply --json
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

The JSON envelope format is a stable contract (`docs/public-contracts.md` Section 11):

```json
{
  "command": "fix",
  "status": "success",
  "data": { "pending_patch_path": "...", "test_command": "pytest -q", "test_exit_code": 1 }
}
```

The `error` field is present only when non-null. Use `"error" in json.loads(output)` to test
for errors.

## Install

From a checkout of this repository:

```bash
uv sync
uv run sac --help
uv run sac doctor
```

For a local command you can run from demo projects:

```bash
uv tool install .
sac doctor
```

Expected result: `sac doctor` prints a table with Python, project root, config,
and command checks.

## Model Configuration

SafeCode defaults to the deterministic `mock` provider. That is the best mode
for the demo workflows and local regression tests:

```bash
sac config init
sac config show
sac ask "What is this project?"
```

To use an OpenAI-compatible provider, configure the trusted user-level file and
opt the current project into network access. Both sides are required; a project
cannot enable network access or choose a provider by itself.

Trusted user config, usually `~/.safecode/config.toml`:

```toml
[sandbox]
network_enabled = true
network_allowlist = ["api.openai.com"]

[llm]
provider = "openai"
model = "gpt-4.1-mini"
base_url = "https://api.openai.com/v1/chat/completions"
```

Project config, `.sac/config.toml`:

```toml
[sandbox]
network_enabled = true
network_allowlist = ["api.openai.com"]
```

Then run:

```bash
export SAFECODE_LLM_PROVIDER=openai
export SAFECODE_LLM_MODEL=gpt-4.1-mini
export OPENAI_API_KEY=...
sac ask "What is this project?"
```

The model can propose text, plans, tool intents, and patches, but writes still
go through SafeCode patch parsing, validation, diff review, checkpointing, and
approval.

## First Task: Failing-Test Repair

Start from the repository root after installing `sac`:

```bash
sac demo materialize failing-test-repair
cd examples/demo-workflows/failing-test-repair
```

Run the existing test. This demo intentionally starts red:

```bash
sac test run --yes
```

Expected result: pytest runs through SafeCode policy and reports a failure for
`add(2, 3)`.

Ask SafeCode to prepare the fix:

```bash
sac edit "Fix the calculator add function so the existing failing test passes."
```

Expected result: SafeCode prints a diff and saves `.sac/pending_patch.json`.
No source file has been modified yet.

Review the diff, then apply it:

```bash
sac apply
```

Expected result: SafeCode shows a patch apply checkpoint. Confirm only when the
diff changes `src/calculator.py` from subtraction to addition.

Run tests again:

```bash
sac test run --yes
```

Expected result: pytest passes, and audit history records the test and patch
events.

```bash
sac history
```

## Safety Model

SafeCode's core boundary is proposal before mutation:

- `sac edit` creates a pending patch and diff; it does not write target files.
- `sac apply` validates the patch again, creates a checkpoint, asks for human
  approval, applies the patch, runs configured hooks through policy, and writes
  audit events.
- `sac test run` detects or accepts a test command, evaluates shell policy, and
  runs through `ShellRunner`.
- High-risk shell commands remain blocked even with `--yes`.
- Project config cannot lower user-level safety settings.
- Network access is disabled by default. Real LLM mode needs trusted user and
  project network opt-in.
- Secret-like files are skipped during context collection.
- Runtime errors are written under `.sac/logs/runtime.jsonl`.

Useful inspection commands:

```bash
sac history
sac report
sac logs show --level error --traceback
sac config show
```

## Rollback

Every successful apply creates a checkpoint before files are changed. To undo
the most recent apply from the demo project:

```bash
sac rollback --last
sac test run --yes
```

Expected result: `src/calculator.py` returns to the original intentionally
broken implementation, so the demo test fails again. That failure is useful: it
proves the rollback restored the pre-apply state.

You can inspect rollback evidence with:

```bash
sac history
```

Look for `checkpoint_created`, `patch_applied`, and `rollback_completed` events.

## Project Command Profile (v4.2, EXPERIMENTAL)

v4.2 adds a project command profile that stores detected test/lint/typecheck/build
commands per project, persisted to `.sac/project_profile.json`. All profile
commands are **EXPERIMENTAL** and may change in future releases.

### Detecting commands

```bash
sac profile detect       # detect and save test/lint/typecheck/build for this project
sac profile show         # show the current profile
sac profile show --json  # machine-readable profile output
```

SafeCode detects commands for Python (pytest/ruff/mypy), Node.js (npm/pnpm/yarn
scripts), Go (`go test`/`go vet`/`go build`), and Rust (cargo). If a tool binary
is not installed, it is marked `missing_dependency=true` but kept visible so you
can decide how to handle it (install the tool or override the command).

### Overriding commands

```bash
sac profile set test "pytest -q --tb=short"  # override the test command
sac profile set lint "ruff check src/"        # override the lint command
sac profile clear test                        # restore the detected test command
```

The `set` command parses the string with `shlex.split` and rejects shell
metacharacters (`;`, `|`, `&`, `$`, `` ` ``, newline) for safety.

### Running suite commands

```bash
sac run --suite test       # run the profile test command through policy checks
sac run --suite lint       # run the profile lint command
sac run --suite typecheck  # run the profile typecheck command
sac run --suite build      # run the profile build command
```

Suite commands are validated through the same policy gates as `sac run <cmd>`.
High-risk commands remain blocked. Exit codes 125 (approval required) and
126 (blocked) are preserved per v2.8.8 semantics.

### Fix command integration

`sac fix` consults the profile test command automatically:

```bash
sac profile detect         # detect test command
sac fix                    # uses profile test command → proposes patch
sac fix --test-command "go test ./..."  # explicit override still wins
```

Precedence: `--test-command` explicit override > profile test command > auto-detect.
The profile is never modified by `sac fix`.

### Doctor integration

`sac doctor` now reports project tooling status:

```
project_tooling_test        PASS  test: pytest -q
project_tooling_lint        PASS  lint: ruff check .
project_tooling_typecheck   SKIP  typecheck: tool missing (mypy)
project_tooling_build       SKIP  build: not detected
```

Missing tools are reported as SKIP (not FAIL) to avoid alarming users who do
not use that tool. Install the tool or run `sac profile set <kind> <cmd>` to
configure a replacement.

## Agent journal — typed steps (EXPERIMENTAL, v4.11.1+)

Agent sessions record structured events in append-only journal files at:

```
.sac/agent_journals/<session_id>.jsonl
```

Since v4.11.1 the journal also records `typed_step` and `typed_result` events
alongside the existing legacy events. These carry a step classification
(`kind`, `status`, `requires_approval`) derived from the agent routing path.

### Reading the journal

```bash
sac agent journal           # render current session journal as Markdown
sac status --json           # includes agent_plan field with latest typed result
```

The `agent_plan` field in `sac status --json` returns:

```json
{
  "agent_plan": {
    "session_id": "...",
    "goal": "add a DELETE endpoint",
    "steps": ["Inspect ...", "Propose patch ...", "Stop for approval"],
    "last_typed_result": {
      "step_index": 2,
      "kind": "edit",
      "status": "waiting_for_user",
      "summary": "Patch proposal created ...",
      "failure_category": null
    }
  }
}
```

### Corrupt-line tolerance

Each journal line is parsed independently; a corrupt or future-version line
is skipped without affecting the rest of the journal. Read helpers return
`None` rather than raising when the journal is missing or empty.

All surfaces in this section are EXPERIMENTAL and carry no stable contract.
