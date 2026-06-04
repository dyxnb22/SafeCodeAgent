# SafeCode MVP User Guide

This guide covers the v4.2.x path for a new user: install SafeCode, set up
your provider, run a coding task, fix a failing test, and review/apply the
proposed patches safely.

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

## Machine-readable output

Most commands support `--json` for scripting:

```bash
sac fix --json
sac edit "task" --json
sac ask "question" --json
sac apply --json
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
