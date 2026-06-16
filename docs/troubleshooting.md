# Troubleshooting SafeCode Agent

## Diagnostics First

Before debugging manually, run the built-in diagnostics:

```bash
sac doctor
```

`sac doctor` checks: Python version, project root detection, config file,
approval directory, LLM provider, last session cost, and package version
against PyPI.

For release-related issues:

```bash
sac release preflight
```

---

## Common Issues

### "No pending patch to apply"

**Cause:** `sac apply` was run without a prior `sac edit`, or the pending
patch was already applied or rejected.

**Fix:** Run `sac edit "your task"` first. If the patch was already applied,
check `sac history` or the audit log.

---

### "Command blocked by policy"

**Cause:** The shell command you asked SafeCode to run is classified as
high-risk or is not in the allowed command list for your current policy preset.

**Fix:**
1. Run `sac config policy-audit` to see the effective policy.
2. If you intended to run the command, check that your policy preset allows it:
   `strict` has the fewest allowed commands; `experimental` allows more.
3. High-risk commands are blocked in all presets — this is intentional.

See [README.md](../README.md#policy-presets) for preset descriptions.

---

### "Network access is disabled"

**Cause:** Network access is `false` in all policy presets by default. Real
LLM calls require the network to be enabled.

**Fix:** Add to your user-level config (`~/.sac/config.toml`):

```toml
network_enabled = true
network_allowlist = ["api.openai.com"]
```

Both lines are required. A project-level config cannot enable network access
by itself. See [docs/mvp-user-guide.md](mvp-user-guide.md#model-configuration).

---

### "Approval not found" or "approval expired"

**Cause:** Sandbox approvals are single-use and bound to the project root.
An approval created for one project root is not valid in another.

**Fix:**
- Run `sac sandbox pending` to see pending proposals.
- Run `sac sandbox approve <id>` to create a new approval.
- Approvals live outside the project root; check your `SAFECODE_APPROVAL_DIR`.

---

### "Audit anchor mismatch" or "integrity failure"

**Cause:** The audit log JSONL file has been modified since the last anchor
was written, or the anchor file is missing.

**Fix:**
- Do not manually edit `.sac/logs/events.jsonl`.
- If the log was accidentally modified, the safest recovery is to archive it
  and start a fresh session.
- The anchor lives outside the project root (`SAFECODE_APPROVAL_DIR`).

---

### "Version mismatch between pyproject.toml and safecode.__version__"

**Cause:** The package was installed from a source tree where the version
strings are out of sync.

**Fix:** Run `sac release check` to see the mismatch details. If you are
developing locally, run `sac release bump X.Y.Z` to update both files, then
reinstall with `uv sync`.

---

### LLM returns empty or malformed output

**Cause:** The model returned a response that failed schema validation.
SafeCode will retry once (`RecoverableContractFailure`) and then stop.

**Fix:**
1. Check `sac logs show --level error` for the structured error.
2. Try a different model or check your API key.
3. If using a custom `base_url`, verify the API is OpenAI-compatible.

---

### "sac rollback --last" does nothing

**Cause:** No checkpoint was written before the last apply, or the checkpoint
was already consumed.

**Fix:**
- Checkpoints are written automatically before every `sac apply`. If you
  modified files manually after applying, `sac rollback` only undoes the last
  `sac apply`.
- Use `sac history` to see available checkpoints.

---

## Local Git Delivery Issues (v4.5, EXPERIMENTAL)

### Dirty unrelated changes

**Cause:** `sac apply` or `sac commit` found unrelated tracked or staged
changes outside the current task files. Untracked files inside directories
touched by the task patch are also blocked.

**Fix:**
- Run `git status --short` and inspect the unrelated files.
- Commit or stash unrelated tracked changes before retrying.
- Use `--allow-unrelated-changes` only after manual inspection.

### Rollback after committed apply

**Cause:** `sac rollback --last` detected that the latest apply appears to
already be committed.

**Fix:** Prefer the printed `git revert <sha>` hint. The default rollback path
never rewrites git history. Use `sac rollback --last --force-uncommit` only
when you intentionally want SafeCode to restore files from the checkpoint and
record the dangerous opt-in audit event.

### Branch creation refusal

**Cause:** `sac branch new <name>` refuses invalid branch names, existing
branches, and dirty unrelated tracked changes. It never force-creates and never
resets.

**Fix:**
- Choose a valid branch name accepted by `git check-ref-format --branch`.
- Pick a branch name that does not already exist.
- Clean or stash unrelated tracked changes, then rerun.

### Unknown task files for commit or diff

**Cause:** SafeCode could not derive a task file set from pending patch,
applied checkpoint, audit, or task sidecar metadata.

**Fix:**
- Run `sac status` and confirm the intended task is CURRENT.
- Use `sac diff --task <task-id>` with an explicit task id.
- If no SafeCode metadata exists for those files, commit manually with git.

---

## Project Memory Issues (v4.6, EXPERIMENTAL)

### Pinned file missing

**Cause:** A path in `.sac/memory/pinned-files.txt` no longer exists. Context
selection reports this as `pinned_missing` metadata.

**Fix:**
- Run `sac memory show --pinned`.
- Recreate the file if it should still guide context.
- Or remove it with `sac memory unpin <path>`.

### Pinned file outside project root

**Cause:** `sac memory pin <path>` refuses paths that resolve outside the
project root. This prevents pinned files from bypassing context boundaries.

**Fix:**
- Pin a project-relative path such as `sac memory pin src/app.py`.
- Move external notes into the project only if they are safe to include.

### Memory secret rejection

**Cause:** `sac memory add-note` or a memory write contained obvious
secret-like text such as tokens, API keys, private keys, or passwords.

**Fix:**
- Remove the secret value and store only the safe fact you wanted SafeCode to
remember.
- Rotate any credential that may have been copied into a terminal or file.

### Recent failure context too stale

**Cause:** `sac fix` includes the newest three redacted recent failures. If the
project has changed substantially, old failures may be less useful.

**Fix:**
- Inspect recent failures with `sac memory show --recent-failures`.
- Clear stale entries with `sac memory clear --recent-failures --yes`.
- Rerun `sac fix` to record fresh failure context.

---

## Runtime Logs

For detailed error context:

```bash
sac logs show --limit 20
sac logs show --level error --traceback
```

Runtime logs are structured JSONL at `.sac/logs/runtime.jsonl`. Each entry
includes component, level, message, error type, traceback, optional
experimental `failure_category`, and extra metadata.

## Failure Taxonomy (v4.7, EXPERIMENTAL)

Use the read-only failure inspector first:

```bash
sac debug last-failure
sac debug last-failure --task <task-id> --json
```

The category names below are experimental runtime debugging labels, not stable
public contracts. The suggested command must match the code table.

| Category | Meaning | Likely Cause | Suggested Command |
|---|---|---|---|
| `model_output_invalid` | The model response did not match the expected agent schema. | Provider returned malformed JSON, wrong response type, or incomplete tool intent. | `sac logs show --level error --traceback` |
| `patch_parse_failed` | SafeCode could not parse the proposed patch text. | The model emitted an invalid patch or mixed prose into patch content. | `sac edit --retry-from-last-failure "<task>"` |
| `patch_apply_conflict` | Patch validation, preview, apply, or rollback could not safely continue. | Files changed since proposal, patch target missing, or checkpoint/apply validation failed. | `sac apply` |
| `command_timeout` | A controlled command exceeded its timeout. | Test/profile command hung, took too long, or needs a narrower target. | `sac debug last-failure` |
| `command_blocked_by_policy` | Command execution was refused by SafeCode policy or approval gates. | High-risk command, unapproved medium-risk command, or blocked MCP/write action. | `sac run "<command>" --yes` |
| `network_disabled` | A command or provider path needed network access but policy disabled it. | Network defaults are off or target host is not allowlisted. | `sac doctor` |
| `provider_auth_failed` | Provider authentication failed. | Missing, revoked, or incorrect API credential. | `sac setup --wizard` |
| `provider_unavailable` | Provider request failed outside authentication. | Provider outage, rate limit, unsupported endpoint, or transport failure. | `sac doctor` |
| `dependency_missing` | A required local executable or dependency was not found. | Test/profile tool is absent from PATH or project tooling is not installed. | `sac doctor` |
| `sandbox_preflight_failed` | Sandbox executor promotion preflight did not pass. | Backend unavailable, env opt-in missing, or executor smoke check failed closed. | `sac sandbox executor-preflight <backend>` |
| `interrupted` | A supported command was interrupted with Ctrl-C. | User interrupted edit/fix/run while a task was active. | `sac resume` |
| `loop_no_progress` | Fix watch saw repeated equivalent failure output. | Consecutive repair attempts hit the same redacted failure-tail hash. | `sac status` |
| `loop_stuck` | Agent loop emitted the same tool intent repeatedly. | The loop could not choose a new safe next action for the task. | `sac status` |
| `budget_exceeded` | A per-task loop budget was exceeded. | Step or time budget was reached before completion. | `sac task budget show` |
| `unknown` | SafeCode found a failure but could not classify it more specifically. | Legacy logs, unexpected exception shape, or incomplete failure metadata. | `sac logs show --level error --traceback` |

For a portable local diagnostic archive:

```bash
sac debug bundle --out safecode-debug.tar.gz
```

The bundle is redacted, excludes project source code, verifies audit integrity
before including audit events, and refuses to overwrite an existing path unless
you pass `--force`.

---

## Project Profile Tool Missing (v4.2, EXPERIMENTAL)

If `sac doctor` reports `project_tooling_<kind>: SKIP — tool missing (<binary>)`,
the tool binary is not on your `PATH`. You have two options:

**Option 1 — Install the tool:**
```bash
# Python: install mypy for typecheck
pip install mypy

# Node: install eslint for lint
npm install -D eslint

# Go: go vet is built-in; no separate install needed

# Rust: install cargo via rustup
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

**Option 2 — Override the command in the profile:**
```bash
sac profile set typecheck "python -m mypy ."
sac profile set lint "npx eslint ."
```

Run `sac profile detect` again after installing the tool to refresh
`missing_dependency` state.

---

## Fix Watch Loop Issues (v4.3, EXPERIMENTAL)

### `loop_no_progress`

**Cause:** `sac fix --watch` saw the same bounded redacted failure-tail hash in
two consecutive failing fix iterations. SafeCode stops instead of proposing
another patch that is unlikely to move the task forward.

**Fix:**
- Run `sac status` to inspect the current task and next step.
- Inspect the failing test output manually.
- Adjust the task, profile test command, or code before rerunning
  `sac fix --watch`.

### `command_timeout`

**Cause:** The selected test or suite command exceeded the timeout budget.
The command exits 124 and SafeCode records `failure_category: command_timeout`.

**Fix:**
```bash
sac fix --watch --timeout-seconds 300
```

If the command normally takes longer, set a larger timeout. If it is hanging,
run the profile command manually through `sac run --suite test` or inspect the
test process.

### Max iterations reached

**Cause:** The current task has already recorded the maximum number of fix
proposals allowed by `--max-iterations` (default 3).

**Fix:**
- Run `sac status`.
- Review prior pending/applied patches and the task sidecar.
- Rerun with a larger budget only after manual inspection:
  `sac fix --watch --max-iterations 5`.

### Blocked suite command

**Cause:** `sac fix --watch --rerun-suite all` ran a profile suite command that
SafeCode command policy blocked. High-risk commands remain blocked even when
selected from the profile.

**Fix:**
- Run `sac profile show`.
- Replace the unsafe suite command:
  `sac profile set lint "ruff check ."`.
- Rerun `sac fix --watch --rerun-suite all`.

### Missing profile suite

**Cause:** `--rerun-suite all` found no command for one of
`test`, `lint`, `typecheck`, or `build` in `.sac/project_profile.json`.

**Fix:** Missing suites are skipped rather than treated as failures. To add one:

```bash
sac profile detect
sac profile set typecheck "mypy ."
```

---

## Resume / Recovery / Budgets (v4.4, EXPERIMENTAL)

### Interrupted tasks

**Cause:** Ctrl-C interrupted `sac edit`, `sac fix`, `sac fix --watch`, or
`sac run`. SafeCode records the current task as `interrupted` and exits 130.

**Fix:**
```bash
sac resume
sac status
```

Review the redacted resume summary and follow the next safe step. `sac resume`
does not auto-apply patches or auto-run commands.

### Resume refuses closed tasks

**Cause:** The selected task is `closed`. Closed tasks are not resumable.

**Fix:**
```bash
sac task new "Continue from closed work"
```

### `budget_exceeded`

**Cause:** A per-task experimental budget was exceeded. The marker records
which budget tripped, such as `steps` or `time_seconds`.

**Fix:**
- Run `sac task budget show`.
- Inspect the current task with `sac status`.
- Increase the budget only after review:
  `sac task budget set --steps 12 --time-seconds 900`.

### `loop_stuck`

**Cause:** The agent loop emitted three identical consecutive task-scoped tool
intents: `(type, target, tool_name, description)`.

**Fix:**
- Run `sac status`.
- Inspect the task and journal before retrying.
- Change the task goal or context if the loop keeps choosing the same action.

---

---

## AI Shell Issues (v4.9, EXPERIMENTAL)

### "Cannot apply in non-TTY mode"

**Cause:** `/apply` or `/commit` was run in non-TTY mode (e.g., piped input or
`--non-tty` flag).

**Fix:** Run `sac apply` or `sac commit` directly from a TTY shell. The AI shell
never auto-applies in non-TTY mode by design.

### "Intent routing not available"

**Cause:** The router module is not importable (package not fully installed, or
import error).

**Fix:** Run `sac doctor` to check the installation. Then use slash commands
(`/status`, `/overview`, `/debug`, `/help`) until the router is available.

### Shell session file is corrupt

**Cause:** A `.sac/shell/<session-id>.json` file is missing or truncated.

**Fix:** The shell reads corrupt files fail-safe (returns None and creates a new
session). The corrupt file can be deleted manually from `.sac/shell/`.

### "Overview unavailable"

**Cause:** The `build_project_overview` function encountered an error (e.g.,
git not installed, no read permission).

**Fix:** Run `sac doctor`. Check that `git` is available in your PATH. Use
`/status` and `/debug` as alternatives.

---

## Agent Loop Smoke Failures (v4.11, EXPERIMENTAL)

### `sac smoke agentic` reports a failed scenario

**Cause:** One of the deterministic mock-only agentic scenarios no longer
matches the expected plan/edit/apply/validation/resume flow.

**Fix:**
```bash
sac smoke agentic --json
sac smoke agentic --only <scenario-name>
```

Inspect the reported `step_kinds`, `final_status`, and `failure_reason`. The
smoke suite is local-only: it should not require provider credentials, network
access, commits, pushes, or patches to the SafeCode repository.

### `loop_no_progress` in agentic smoke

**Cause:** The validation-failure scenario intentionally verifies the stop
condition for an unchanged failure-tail hash.

**Fix:** Treat this as expected when the scenario passes. If the scenario fails,
inspect the typed journal events under the temporary smoke project and confirm
that validation failure and repair events are still appended in order.

---

## Multi-Tool Turn Issues (v4.22, EXPERIMENTAL)

### Per-turn tool cap hit

**Cause:** The agent emitted more than 20 tool calls in a single turn.

**Fix:** Re-send your message. The agent will continue from where it stopped.
Alternatively, break the request into smaller parts (e.g., "fix the auth
module" instead of "fix everything in src/").

### `/clear` not fully resetting context

**Cause (pre-v4.22):** `/clear` only reset the display; agent session state
was preserved. Fixed in v4.22 (B10): `/clear` now calls `AgentSessionStore.clear()`.

**Fix:** Update to v4.22+; then `/clear` resets both display and agent state.

### `/undo` says "No checkpoint to roll back"

**Cause:** No write-tool checkpoint exists in `.sac/checkpoints/`.

**Fix:** `/undo` only rolls back `edit_file` and `write_file` calls; `read_file`,
`search_files`, etc. do not create checkpoints. If you used a `sac apply` workflow,
use `sac rollback --last` instead.

### Shell exits silently on Ctrl-D / EOF (pre-v4.22)

**Cause (pre-v4.22):** EOF caused a silent exit. Fixed in v4.22 (B11): the shell
now prints `[exiting shell]` before exiting on EOF.

## Write Tool Issues (v4.21, EXPERIMENTAL)

### `edit_file` — old_string not found

**Cause:** The exact string in `old_string` does not appear in the file.

**Fix:** Use `read_file` first to confirm the current file content, then
adjust `old_string` to match exactly (whitespace and line endings included).

### `edit_file` — old_string matches more than once

**Cause:** The string appears multiple times; the tool refuses to apply
to avoid ambiguous edits.

**Fix:** Include more context in `old_string` to make it unique. For
example, include the surrounding function signature or comment.

### `write_file` blocked for protected directory

**Cause:** The path resolves into `.sac/`, `.git/`, or another SKIP_DIR.

**Fix:** These directories are intentionally write-protected. Use standard
SafeCode commands to modify `.sac/` state (e.g., `sac task new`).

### Rollback after a native tool edit

**Cause:** An `edit_file` or `write_file` call produced an unwanted result.

**Fix:** Every write tool call creates a checkpoint before executing.
Run `sac rollback --last` to undo the most recent write, or
`sac rollback --list` + `sac rollback --checkpoint <id>` for a specific one.

### Disk-full error during apply (B7)

**Cause:** `edit_file` / `write_file` raised `OSError` (ENOSPC) mid-apply.

**Fix:** Free disk space, then re-run the command. The previous checkpoint
was created before the error, so `sac rollback --last` restores the pre-edit
state if the file was partially written.

### `run_command` blocked as high-risk

**Cause:** The command matches a high-risk pattern in the policy engine
(e.g., `rm -rf`, network calls without `network: true`, etc.).

**Fix:** Review the policy with `sac config show`. For intentionally risky
commands, consider running them manually in your terminal rather than
through the agent.

## Native Tool Issues (v4.20, EXPERIMENTAL)

### `read_file` blocked with "outside the project root"

**Cause:** The path resolves outside the project directory (e.g., `../../etc/passwd`).

**Fix:** Use paths relative to the project root. Absolute paths are validated
against the root boundary.

### `read_file` blocked as sensitive

**Cause:** The file matches a sensitive-path pattern (`.env*`, `*.pem`, `*.key`,
`id_*`, `*secret*`, `*password*`, etc.) or is in a skipped directory (`.git/`, `.sac/`).

**Fix:** These files are intentionally excluded for security. If you need to inspect
policy configuration, check `src/safecode/context/collector.py:SENSITIVE_PATTERNS`.

### Large file or truncated results

**Cause:** `read_file` caps at 400 lines; `list_files` caps at 500 entries;
`search_files` and `grep_files` cap at 100 results.

**Fix:** Use `start_line`/`end_line` parameters on `read_file` for large files.
Use `path` to narrow the search scope for search/grep tools.

### File tree shown as truncated in context

**Cause:** `context.max_tree_files` cap was reached during context collection (B5 fix).
The model sees `file_tree_meta.truncated: true` in its context.

**Fix:** The agent can use `list_files` or `search_files` to discover more files
that did not fit in the initial context pack.

## Reading Local State

SafeCode stores task sidecars, audit events, memory, and checkpoints under
`.sac/`. Two read-only observability commands surface this data without
modifying anything:

- **`sac task stats [--task <id>] [--json]`** — iteration histogram, budget
  usage, pinned file count, last command, and audit trace count for one task.
  Falls back to CURRENT task when `--task` is omitted.
- **`sac memory size [--json]`** — byte and file count per `.sac/` scope
  (`audit`, `checkpoints`, `memory`, `runtime_logs`, `tasks`, `other`). Reports
  `exists: false` when `.sac/` has not been created yet.

Both commands are EXPERIMENTAL, never mutate, and never call the model,
network, or shell.

---

## Reliability Hardening Issues (v4.25, EXPERIMENTAL)

### Checkpoint Integrity Error

**Symptom:** `sac rollback` or `/undo` raises `CheckpointIntegrityError` with a message
like `"Checkpoint integrity failure: backup sha256 mismatch for 'src/foo.py' in
checkpoint 'chkpt-xyz'."`.

**Cause (B13 fix):** The backup file stored in `.sac/checkpoints/<id>/files/` has been
corrupted or modified since the checkpoint was created. The sha256 hash no longer matches
the value recorded at checkpoint time. SafeCode refuses to restore a corrupt backup.

**Fix:**
1. Do **not** force-rollback — the backup may be unrecoverable.
2. Manually inspect the backup file:
   ```bash
   ls .sac/checkpoints/<id>/files/
   cat .sac/checkpoints/<id>/metadata.json
   ```
3. If the backup is corrupt, delete the checkpoint directory:
   ```bash
   rm -rf .sac/checkpoints/<id>/
   ```
4. Re-apply the original patch from your task context, or manually restore
   the file from git: `git checkout src/foo.py`.

---

### `.sac/` Directory Not Writable

**Symptom:** `sac doctor` reports `FAIL: sac_dir_writable — .sac/ is not writable`
(B14 fix, added v4.25.1).

**Cause:** The `.sac/` directory exists but the current user lacks write permission.

**Fix:**
```bash
ls -la .sac/            # inspect permissions
chmod u+w .sac/         # restore write permission for your user
# or on systems with restricted permissions:
sudo chown -R $USER .sac/
```

---

### Low Disk Space Warning

**Symptom:** `sac doctor` reports `WARN: disk_space — Low disk space: Xmb free`
(B14 fix, added v4.25.1).

**Cause:** Available disk space is below 100 MB. This is a WARN (not FAIL) — SafeCode
can still operate, but apply operations that write checkpoint backups may fail.

**Fix:**
```bash
df -h .                  # see available space
# Free space before using sac apply or sac edit:
# rm large files, empty Trash, clear unused Docker images, etc.
```

---

### Provider Not Reachable After `sac init`

**Symptom:** After running `sac init`, a yellow warning appears:
`"Warning: could not reach the provider API. Credentials may be missing or invalid."`
(B15 fix, added v4.25.1).

**Cause:** The live connectivity ping performed after config write failed. Common causes:
- API key is invalid or expired.
- Network is not enabled or the provider host is blocked by firewall.
- The provider API has a temporary outage.

**Fix:**
```bash
sac doctor --live        # full live connectivity check with verbose output
# Re-run init with correct credentials:
sac init --provider anthropic --api-key sk-ant-...
```

---

## Context Intelligence Issues (v5.3, EXPERIMENTAL)

### Why is the agent not reading the right files?

Import-graph seeding activates automatically when you mention a file path in
your goal. If the agent is reading irrelevant files:

1. **Mention the file explicitly:** "Edit `src/auth/login.py` to add MFA support"
   triggers seeding; "add MFA support" does not.
2. **Use manual `read_file` first:** in the shell, start with
   `/read src/auth/login.py` before your main goal.
3. **Pin the file in memory:** `sac memory pin src/auth/login.py` ensures the
   file is always considered in context selection.

### What happened to my earlier tool results?

Long sessions trigger automatic context compaction. A notice appears when it
fires:

```
[Context compacted: ~3200 → ~600 tokens (12 observations archived)]
```

The raw observations are archived (not deleted) to:
```
.sac/sessions/<session-id>/observations_compacted_N.jsonl
```

You can read the archives at any time:
```bash
cat .sac/sessions/<session-id>/observations_compacted_1.jsonl | python3 -m json.tool
```

The model's compact summary replaces the raw observations in future calls. If
the summary missed something important, you can restart the session with
`/clear` and re-state the relevant context in your next message.

### Compaction is costing extra tokens

Each compaction costs one LLM call (the summarisation prompt). To raise the
threshold so compaction fires less often:

In your user config (`~/.safecode/config.toml`):
```toml
[context]
compaction_threshold_ratio = 0.80   # trigger at 80% instead of 60%
```

Note: project-local config cannot change this setting.

To see how many compaction calls were made in a session:
```bash
sac audit query --type tool_call_compact
```

## Display Issues (v5.2, EXPERIMENTAL)

### Why doesn't `/cost` show a price?

Two possible causes:

1. **Mock provider:** When `sac shell` runs with the default `mock` provider,
   no real API calls are made and cost tracking is disabled. `/cost` will
   show "Provider: mock (cost tracking disabled)".

   To see costs, set up a real provider with `sac init` or `sac provider add`.

2. **No usage yet in this session:** If you just opened the shell and haven't
   sent any messages, `/cost` will show "No token usage recorded yet."

### How do I see the full output of a command?

`run_command` output longer than 40 lines is collapsed in the shell display.
The full output is always available in the audit log:

```bash
sac audit query --type tool_call_command --task <task-id>
```

For scripting or CI where you need full output in the shell:

```bash
sac shell --full-auto --command-delay-ms 0 --json  # full output in JSON envelope
```

In JSON output mode, the full `output` field is always untruncated.

### How do I see all files edited in a session?

At the end of every `--auto-edit` or `--full-auto` session, a summary line
shows how many files were edited and the rollback command:

```
Session: sess-abc | Files edited: 4 | Undo all: sac rollback --session sess-abc
```

In the shell, use `/history` to see recent turns with their intent labels and
which files were mentioned.

## Trust Mode Issues (v5.1, EXPERIMENTAL)

### How do I undo everything from an auto-edit session?

When a `--auto-edit` or `--full-auto` session ends, the session ID and a
rollback hint are printed:

```
Session: sess-abc | Files edited: 4 | Undo all: sac rollback --session sess-abc
```

Run the printed command to roll back all checkpoints from that session in
reverse order (most-recent first):

```bash
sac rollback --session sess-abc
```

You can also undo one file at a time:
```bash
sac rollback --last         # most recent checkpoint
sac rollback --list         # see all available checkpoints
```

### Auto-edit edited too many files without asking

SafeCode Agent has a **file count guard**: if the agent would auto-apply more
than 10 edits in one session, it pauses and asks for confirmation before
continuing.

If you hit this guard and want to continue, type `y` at the prompt. To reduce
the chance of surprises, be more specific in your goal: instead of "refactor
everything", try "rename AuthManager to TokenManager in src/auth/".

### Full-auto ran a command I didn't expect

In `--full-auto` mode, each `run_command` prints a preview line before
executing:

```
  → run_command  pytest -q tests/
```

By default there is a **500 ms grace period** before execution. Press **Ctrl-C**
during this window to abort the specific command (the agent session continues;
only that one command is skipped).

To increase the grace period:
```bash
sac shell --full-auto --command-delay-ms 2000   # 2 second delay
```

To undo the effects of a command that already ran:
```bash
sac rollback --last    # if the command made file changes via edit_file
```
Note: `run_command` side effects (e.g. deleted files, installed packages) are
not checkpointed. Use full-auto only for commands you would trust in a script.

High-risk commands (`rm -rf /`, commands outside the project root, etc.) are
**always blocked** regardless of trust mode.

## MCP Integration Issues (v5.4, EXPERIMENTAL)

**MCP tool not showing in `sac mcp list-native`:**

1. Check `sac mcp doctor <server>` — server may be disabled or scope=denied.
2. Schema metadata must exist in `MCPSchemaStore` with `classification="read"`.
   Without schema metadata the bridge finds no tools to register.
3. Run `sac mcp stdio-discover <server>` to see what the server actually reports
   (requires `argv` configured in `.sac/mcp.toml`).

**MCP write tool blocked:**

- Server scope must be `write_proposal_required` in `.sac/mcp.toml`.
  Servers with `scope = "read_only"` (the default) block write tool proposals.
- Write tools must have schema metadata with `classification = "write"`.

**MCP tool name collision:**

All MCP tools are prefixed `mcp_<server>_<tool>`.  If two servers expose the
same raw tool name they get distinct native names (`mcp_srvA_list` vs `mcp_srvB_list`).

**`sac mcp execute` fails without grant:**

`sac mcp execute` requires a valid approval grant in `~/.sac/mcp/approvals/`
(override: `SAFECODE_MCP_APPROVAL_DIR`).  Grants are single-use.  Create a
grant via the shell approval flow or `MCPApprovalStore.grant(proposal_id)`.

**MCP stdio discovery times out:**

Increase the timeout: `sac mcp stdio-discover <server> --timeout 30`.
Ensure the server binary is reachable (`sac mcp doctor <server>` shows binary path).

## Getting More Help

- Run `sac --help` for command reference.
- Run `sac <command> --help` for per-command options.
- See [docs/mvp-user-guide.md](mvp-user-guide.md) for a guided walkthrough.
- See [docs/tutorials/ai-shell-first-hour.md](tutorials/ai-shell-first-hour.md) for the AI shell tutorial.
- See [docs/public-contracts.md](public-contracts.md) for stable API contracts.
- File issues at the project repository.
