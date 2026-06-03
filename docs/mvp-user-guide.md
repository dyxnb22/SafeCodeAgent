# SafeCode MVP User Guide

This guide covers the v3.7.x path for a new user: install SafeCode, set up
your provider, run a coding task, fix a failing test, and review/apply the
proposed patches safely.

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
