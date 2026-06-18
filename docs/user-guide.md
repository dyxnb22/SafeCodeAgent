# SafeCode User Guide

This guide is the current first-run and daily workflow path for SafeCode:
install the CLI, verify the environment, configure a model when needed, run a
demo, repair a failing test, and safely review, apply, or roll back proposed
patches.

Start with the guided walkthrough:

- [From Task to Tested Commit](tutorials/from-task-to-tested-commit.md)
- [FastAPI todo example](../examples/fastapi-todo/)
- [Recorded demo transcript](../examples/fastapi-todo/demo/expected-transcript.md)

For command details after the first run, use [reference/commands.md](reference/commands.md).

## Recommended First Path

```bash
uv sync
uv run sac doctor
uv tool install .
sac quickstart
sac demo materialize failing-test-repair
cd examples/demo-workflows/failing-test-repair
sac test run --yes
sac edit "Fix the calculator add function so the existing failing test passes."
sac apply
sac test run --yes
sac history
sac rollback --last
```

Nothing is written by `sac edit`; it saves a pending patch and prints a diff.
`sac apply` is the approval point. It validates again, creates a checkpoint,
asks for confirmation, applies, and writes audit events.

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

## From Local Edits to Open PR (v4.24, EXPERIMENTAL)

Starting with v4.24, the agent can fetch web pages, read GitHub issues/PRs/files,
and open pull requests — all within a single shell session.

**Quick start (requires network: true and `gh` auth):**

```bash
export GITHUB_TOKEN=ghp_...
sac provider add anthropic --model claude-sonnet-4-6 --network
sac shell
```

**Typical workflow:**

```
sac[0]> Read issue #42 in acme/myapp and fix the bug described there.
# Agent calls: github_read_issue → read_file → edit_file (approval) → github_create_pr (approval)
sac[0]> github_push_branch branch=dev/fix-issue-42
```

**Tool overview:**

| Tool | Approval? | Network? | Notes |
|---|---|---|---|
| `web_fetch` | No | Yes | text/HTML only, 50 KB cap, scripts stripped |
| `github_read_issue` | No | Yes | via `gh issue view` |
| `github_read_pr` | No | Yes | via `gh pr view` |
| `github_read_file` | No | Yes | via `gh api repos/.../contents/...` |
| `github_create_pr` | **Yes** | Yes | via `gh pr create`; pauses for confirmation |
| `github_push_branch` | **Yes** | Yes | via `git push -u origin`; pauses for confirmation |

**Safety notes:**
- Write tools always pause for user confirmation before executing.
- `owner`/`repo`/`branch` inputs are validated against safe patterns; shell metacharacters rejected.
- All subprocess calls use `shell=False`; no injection surface.
- `force=true` in `github_push_branch` must be explicitly set; it is not defaulted.
- All tool outputs are redacted and capped before entering model context.

## First-Run with Claude (v4.23, EXPERIMENTAL)

Starting with v4.23.0, SafeCode uses the Anthropic native tool-use API when
the `anthropic` provider is active. The agent sends tool schemas (`read_file`,
`list_files`, `search_files`, `grep_files`, `edit_file`, `write_file`,
`run_command`) as Anthropic `tools` parameters and receives structured
`tool_use` blocks — the same protocol Claude Code itself uses.

**Quick start:**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
sac provider add anthropic --model claude-sonnet-4-6 --network
sac doctor --live     # verifies Anthropic API connectivity (B16 fix)
sac shell             # enter the native-tool-use shell with Claude
```

**What changes with native tool use:**
- Tool calls arrive as structured `tool_use` blocks instead of freeform JSON.
- Empty or malformed content blocks surface as `RecoverableContractFailure`
  (B2 fix) — the loop retries once instead of crashing.
- Stream reads have a 30-second per-chunk timeout (B3 fix); stalled streams
  raise `StreamTimeoutError` and are treated as recoverable.
- `sac doctor --live` now includes an Anthropic API connectivity check that
  sends your API key as an authenticated GET /v1/models ping.

**OpenAI and DeepSeek (v4.23.1):**
OpenAI-compatible providers also use native function calling. DeepSeek
inherits through the OpenAI-compatible path.

```bash
sac provider add openai --model gpt-4o --network
sac doctor --live
sac shell
```

All safety gates are unchanged: every `edit_file` / `write_file` call still
creates a checkpoint before applying; `run_command` still passes through the
shell policy; all tool outputs are redacted before entering model context.

## Provider Profiles

**Mental model: Provider account first, model switch second, project safety third.**

Configure a provider once, then switch models with short aliases:

```bash
sac provider add deepseek       # prompts for API key; writes to trusted user config
sac model flash                 # switch to deepseek-v4-flash (daily default)
sac model pro                   # escalate to deepseek-v4-pro
sac --model deepseek:pro        # one-shot override for this invocation
sac model list                  # show available aliases for active provider
sac provider status             # show effective provider, model, credential source
sac provider list               # list configured provider profiles
sac provider use deepseek       # set active provider
sac provider rm deepseek --yes  # remove a provider profile
```

DeepSeek aliases: `flash` → `deepseek-v4-flash`, `pro` → `deepseek-v4-pro`.
Provider-scoped aliases also work: `deepseek:flash`, `deepseek:pro`.

Inside `sac shell`:
```
/model              show current model and available aliases
/model flash        switch to flash (persisted globally)
/model pro          switch to pro (persisted globally)
/provider status    show provider profile status
```

Profile credentials are stored either in the system keychain (`--store keychain`)
or in the trusted user config (`--store user-config`, `~/.safecode/config.toml`).
Project-local config cannot store credentials or widen user-level network policy.
Environment variables (`DEEPSEEK_API_KEY`, `SAFECODE_LLM_PROVIDER`, `SAFECODE_LLM_MODEL`)
take precedence over persisted profile settings.

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

The command-line path writes the provider, model, and optional API key to the
trusted user config:

```bash
sac model gpt-4.1-mini --provider openai --api-key sk-... --network
sac setup --yes --provider openai --model gpt-4.1-mini --network
```

Trusted user config, usually `~/.safecode/config.toml`:

```toml
[sandbox]
network_enabled = true
network_allowlist = ["api.openai.com"]

[llm]
provider = "openai"
model = "gpt-4.1-mini"
base_url = "https://api.openai.com/v1/chat/completions"
api_key = "sk-..."
```

Project config, `.sac/config.toml`:

```toml
[sandbox]
network_enabled = true
network_allowlist = ["api.openai.com"]
```

Then run:

```bash
sac ask "What is this project?"
```

Environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`DEEPSEEK_API_KEY`, `SAFECODE_LLM_API_KEY`, `SAFECODE_LLM_PROVIDER`, and
`SAFECODE_LLM_MODEL`) still take priority when you want a temporary override.

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

## Daily Workflow Summary

These v4.x workflows are EXPERIMENTAL. They are summarized here so visible
commands are discoverable; full details live in [reference/commands.md](reference/commands.md).
No auto-apply. No step auto-applies or auto-commits.

```bash
sac shell
sac task new "Fix auth regression"
sac profile detect
sac status
sac ask "explain the auth flow"
sac edit "Fix auth regression"
sac fix
sac fix --watch
sac fix --watch --max-iterations 5
sac fix --watch --timeout-seconds 60
sac fix --watch --rerun-suite all
sac apply
sac rollback --last
sac diff --task
sac commit --message-from-task
sac branch new follow-up/auth-cleanup
sac resume
sac task budget show
sac task budget set --steps 8 --time-seconds 600 --retries 2 --tokens 60000
sac run --suite test
sac setup --wizard
sac memory show
sac memory pin src/app.py
sac memory unpin src/app.py
sac memory add-note "health route must stay synchronous"
sac memory clear --recent-failures --yes
sac debug last-failure
sac debug bundle --out safecode-debug.tar.gz
sac audit query --task <task-id>
sac doctor
sac quickstart
sac version
```

Key safety notes:

- `sac fix --watch` never applies patches automatically; run `sac apply` after
  reviewing the pending diff.
- `sac resume` is passive and never runs `edit`, `fix`, `apply`, or a shell
  command by itself.
- `sac commit` is task-aware and protected by a dirty-tree guard.
- Project memory uses `.sac/memory/project.md` and `.sac/tasks/<task_id>/memory.md`;
  recent failures are bounded and redacted.
- Debug commands are read-only or metadata-only and remain EXPERIMENTAL.

## Inspecting Local State (v4.19, EXPERIMENTAL)

Two read-only observability commands surface what SafeCode has accumulated under
`.sac/` without calling the model, network, or shell.

### `sac task stats` — per-task iteration summary

```bash
sac task stats                    # stats for CURRENT task
sac task stats --task <task-id>   # stats for a specific task (readable even if closed)
sac task stats --json             # machine-readable output
```

Example JSON output:

```json
{
  "task_id": "fix-auth-endpoint-a1b2",
  "status": "open",
  "iterations": {
    "total": 3,
    "last_event": "fix",
    "by_event": {"edit": 1, "fix": 2},
    "by_failure_category": {"budget_exceeded": 1}
  },
  "budget": {"steps": 8, "time_seconds": 600, "retries": 2, "tokens": 60000},
  "pinned_files": {"count": 1},
  "experimental": true
}
```

All text fields (goal, last_command) are redacted. This command never mutates
any `.sac/` file.

### `sac memory size` — .sac/ storage breakdown

```bash
sac memory size          # human-readable table by scope
sac memory size --json   # machine-readable output
```

Reports bytes and file counts per named scope (`audit`, `checkpoints`, `memory`,
`runtime_logs`, `tasks`, `other`). Uses only `Path.stat()` — never reads file
contents. `.sac/` content is local-only; nothing is sent off-machine.

## Project Command Profile (v4.2, EXPERIMENTAL)

Project profiles store detected test/lint/typecheck/build commands in
`.sac/project_profile.json`.

```bash
sac profile detect
sac profile show
sac profile set test "pytest -q --tb=short"
sac profile clear test
sac run --suite test
sac run --suite lint
sac run --suite typecheck
sac run --suite build
```

`sac fix` consults the profile test command automatically. Explicit
`--test-command` overrides still win. Missing tools are reported as SKIP by
`sac doctor`, not FAIL.

## Exploring a Codebase with Native Tools (v4.20, EXPERIMENTAL)

Starting with v4.20.0, the agent can call four read-only tools directly
rather than relying on pre-packaged context:

| Tool | What it does |
|---|---|
| `read_file` | Read a file by path (up to 400 lines, secrets redacted). |
| `list_files` | List files/directories under a project path. |
| `search_files` | Literal substring search across project files. |
| `grep_files` | Regex search using Python `re`, with optional `case_insensitive`. |

All four tools:
- Are **auto-approved** — no user prompt needed.
- **Never write** to any file.
- **Validate paths** against the project root (root escapes are blocked).
- **Redact secrets** from all output before the model sees it.
- Are **audited** as `tool_call_read` events.

The agent can now answer "what does `src/auth/login.py` import?" or
"where is `handle_request` defined?" in a single turn without you
having to specify which files to include in context.

## Making Edits with Native Tools (v4.21, EXPERIMENTAL)

Starting with v4.21.0, the agent can make file edits and run commands
through native tools. Each edit is checkpointed so rollback is always
available.

### `edit_file` — approval-gated string replacement

The agent proposes an exact string replacement. You see a diff preview
before it executes. After approval, a checkpoint is created and the file
is modified.

```
edit_file:
  path: "src/auth/login.py"
  old_string: "return None"
  new_string: "return redirect('/dashboard')"
```

**If the match is not unique**, the tool returns an error rather than
applying. This prevents accidental multi-site edits.

### `write_file` — approval-gated create/overwrite

Creates a new file or overwrites an existing one. Also checkpointed.
Blocked for `.sac/`, `.git/`, and other protected directories.

### `run_command` — policy-gated shell execution

Runs a shell command through the same risk-classification and policy
engine as `sac run`. High-risk commands are blocked automatically.

### Rollback after native tool edits

Each `edit_file` or `write_file` creates a separate checkpoint:
```bash
sac rollback --last      # undo the most recent edit
sac rollback --list      # see all available checkpoints
sac rollback --checkpoint <id>  # roll back a specific edit
```

## Working with Large Codebases (v5.3, EXPERIMENTAL)

### Import-graph seeding (C1/C4)

When you ask the agent to edit a specific file, SafeCode automatically traces
its import graph and pre-loads the most relevant related files into context:

```
sac shell --agentic
sac[0]> refactor the auth module in src/auth/login.py
# → SafeCode detects 'src/auth/login.py' in your goal
# → Automatically loads src/auth/session.py, src/auth/models.py (first-degree imports)
# → Agent starts with the right files already in context
```

You can also pass seed files explicitly from the CLI:
```bash
sac edit "update the database connection layer" --seed src/db/connection.py
```

### Git-aware context (C6)

Every session automatically includes recent git activity:
- Last 10 commits with file lists
- Files changed since your branch diverged from `main`/`master`
- High-churn files (frequently modified in the last 30 days)

The agent can use this to understand what you've been working on and connect
your request to recent changes without extra `read_file` calls.

### Context compaction (C2/C3)

Long agent sessions (many tool calls) accumulate observations that can fill the
context window. When the accumulated context exceeds 60% of the model's budget,
SafeCode automatically:

1. Asks the model to summarise what it has learned so far.
2. Archives the raw observations to `.sac/sessions/<id>/observations_compacted_N.jsonl`.
3. Replaces the raw observations with the compact summary in the next call.
4. Prints a notice: `[Context compacted: ~3200 → ~600 tokens (12 observations archived)]`

**To see what was compacted:**
```bash
sac audit query --type tool_call_compact --task <task-id>   # audit events
ls .sac/sessions/<session-id>/observations_compacted_*.jsonl  # raw archives
```

**To change the compaction threshold** (default 60%):
Add to `.safecode/config.toml` (user config only; project config ignored):
```toml
[context]
compaction_threshold_ratio = 0.75   # trigger at 75% instead
```

## Trust Modes (Stable Contract #18)

By default, SafeCode Agent asks for approval before every file edit and command.
SafeCode exposes two optional trust modes that reduce interruptions while
preserving the stable safety invariants in Public Contract #18: checkpoints,
audit trail, rollback, command policy, and session rollback.

### Choosing a trust mode

| Mode | Flags | Edit_file/write_file | Run_command | GitHub writes |
|---|---|---|---|---|
| `suggest` (default) | _(none)_ | prompts | prompts | prompts |
| `auto-edit` | `--auto-edit` | **auto** | prompts | prompts |
| `full-auto` | `--full-auto` | **auto** | **auto** (within policy) | prompts |

### Working at speed with auto-edit

Auto-edit lets the agent rewrite files without pausing per edit, while keeping
command execution gated:

```bash
sac shell --auto-edit
# sac[auto-edit]> refactor the auth module to use the new token format
# → The agent reads files, proposes edits, and applies them automatically.
# → run_command (e.g. pytest) still requires your confirmation.
# Session: sess-abc | Files edited: 4 | Undo all: sac rollback --session sess-abc
```

**File count guard:** if the agent would auto-apply more than 10 edits in one
session without a pause, it stops and asks "About to edit >10 files. Continue?".

### Using full-auto for scripted or CI-like tasks

Full-auto also auto-approves `run_command` within the existing shell policy:

```bash
sac shell --full-auto --command-delay-ms 0   # no delay; for CI/scripting
# sac[full-auto]> run the test suite and fix any failures
#   → run_command  pytest -q tests/          # preview line printed
#   ✓ exit 0 (2.1s)
```

Even in full-auto:
- High-risk commands (`rm -rf /`, network calls without allowlist, etc.) are
  still blocked by the policy engine.
- A preview line prints before each command. With the default 500 ms delay,
  you can press **Ctrl-C** to abort a single command cleanly.
- Full-auto cannot be saved as a default: you must pass it explicitly each session.

### Rollback in auto-edit / full-auto sessions

```bash
sac rollback --last                          # undo the most recent checkpoint
sac rollback --session <session-id>          # undo all edits from one session (printed at exit)
```

The session ID is printed at the end of every `--auto-edit` or `--full-auto`
session. All checkpoints created during the session are listed in reverse order.

## Understanding What the Agent Did (v5.2, EXPERIMENTAL)

### Start in the shell

The recommended interactive entry point is the bare command:

```bash
sac
```

Inside the shell, start with `/status`. It is the workspace dashboard: provider
and model, credential source, task state, active agent session, memory counts,
safety/network state, git state, and the next safe action.

```text
sac[0]> /status
```

Use `/continue` when you want SafeCode to take the next safe step. It will not
apply a pending patch or commit changes automatically; those approval gates still
use `/apply` and `/commit`.

The most useful shell controls are deliberately small:

| Command | Use it for |
|---|---|
| `/status` | See provider/model, current task, active session, memory, safety, git state, and next step. |
| `/continue` | Advance one safe agent step, or get a precise blocker such as missing credential, network off, pending patch, or user input needed. |
| `/ready` | Check whether the active provider/model/network/memory setup is ready. Add `--live` only when you want an opt-in live provider smoke. |
| `/memory` | Inspect approved facts, project notes, recent summaries, pending facts, and pinned files that may enter context. |
| `/memory review` | Review pending learned facts before they become active context. |
| `/memory teach <text>` | Add a non-secret project note that should be visible in future sessions. |
| `/demo` | Show a safe first-run path that exercises status, ask, apply, and undo without auto-committing. |
| `/resume` | Resume the current or most recent agent session context passively; follow with `/continue` when you want action. |

### Shell prompt

The shell prompt now shows turn count, task status, and running cost:

```
sac[0]>                                     # no task, no cost
sac[3 · task:open · 2i]>                   # task active, 2 iterations
sac[5 · task:acti · 3i · ~$0.04]>          # task active + cost (real provider)
```

Cost only appears when a real provider is active (hidden for mock).

### `/cost` — session cost breakdown

```
sac[4]> /cost
Session cost estimate
─────────────────────
Input tokens:    12,340
Output tokens:    1,890
Cache reads:      8,000   (cheaper rate)
Estimated cost: ~$0.065
Provider: anthropic · claude-sonnet-4-6
```

Cost is tracked per-session. If the provider is `mock`, cost tracking is disabled.

### Diff display during approval

When a write tool proposes an edit, the approval prompt shows a compact header:

```
[+12 / -4 lines]  src/auth/login.py
--- a/src/auth/login.py
+++ b/src/auth/login.py
@@ -45,7 +45,15 @@
```

The `[+12 / -4 lines]` header lets you skim a large session's edits quickly.

### Long command output

`run_command` output longer than 40 lines is automatically collapsed:

```
line 0
line 1
line 2
line 3
line 4
--- [45 lines hidden] ---
line 55
line 56
line 57
line 58
line 59
```

The full output is still written to the audit log.

## From Question to Patch in One Turn (v4.22, EXPERIMENTAL)

Starting with v4.22, the agent can execute multiple tool calls per user
message before generating a final response. A single "turn" might look like:

1. **read_file** `src/auth/login.py` — inspect the current implementation
2. **search_files** `"handle_session"` — locate the relevant function
3. **edit_file** `src/auth/login.py` — propose the fix

All of this happens before you see the response. Each `edit_file` creates
a checkpoint, so you can roll back any individual edit with `/undo` or
`sac rollback --last`.

### Shell prompt

The shell prompt now shows the turn count: `sac[0]>`, `sac[1]>`, etc.
This lets you track how many messages you've sent in the current session.

### New shell commands

- `/undo` — Roll back the most recent write-tool checkpoint without leaving
  the shell.
- `/history` — Show the last 10 turns of the current session (input and intent).
- `/tools` — List all available native tools with descriptions and approval flags.
- `/clear` — Resets both the display and the live agent session state (so the
  next message starts with a clean context).

### Per-turn cap

Each turn is capped at 20 tool calls. If the cap is hit, the agent stops
and you see: `"per-turn cap hit — re-send your request to continue"`.

## Machine-readable output

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

## Agent journal — typed steps (EXPERIMENTAL, v4.11.1+)

Agent sessions record structured events in append-only journal files at:

```text
.sac/agent_journals/<session_id>.jsonl
```

```bash
sac agent journal
sac status --json
```

Since v4.11.1 the journal also records `typed_step` and `typed_result` events
alongside existing legacy events. All surfaces in this section are EXPERIMENTAL
and carry no stable contract.

## Extending the Agent with MCP Servers (v5.4, EXPERIMENTAL)

MCP (Model Context Protocol) servers let you add third-party read and write
capabilities to the agent.  When the agentic shell starts it automatically
registers all eligible MCP tools so they appear in the model's tool list.

### Setup — sqlite example

1. Install the server:
   ```bash
   pip install mcp-server-sqlite
   # or: uvx mcp-server-sqlite --help
   ```

2. Create `.sac/mcp.toml`:
   ```toml
   [servers.sqlite]
   command = "uvx mcp-server-sqlite --db-path ./data.db"
   scope   = "read_only"
   enabled = true
   ```

3. Add schema metadata so the bridge knows which tools are read-class
   (without this, tools are not registered in the native dispatcher):
   ```python
   # .sac/mcp_schemas.py  — loaded by your project setup
   from safecode.mcp.schema import MCPToolSchema, MCPSchemaStore
   MCPSchemaStore().register(MCPToolSchema(
       server="sqlite", tool="list_tables", classification="read",
       description="List tables in the SQLite database.", args=("db_path",)
   ))
   ```

4. Check what was registered:
   ```bash
   sac mcp list-native        # shows: mcp_sqlite_list_tables
   ```

5. Start the agentic shell — the agent calls `mcp_sqlite_list_tables` naturally:
   ```bash
   sac shell --agentic
   ```

### Write Tool Approval Flow

For write operations, set `scope = "write_proposal_required"` in `.sac/mcp.toml`.
When the agent calls a write MCP tool:
- A pending proposal is created at `.sac/pending_mcp_call.json`.
- The shell pauses and shows an approval prompt.
- After you approve, the tool executes and the grant is consumed (single-use).

One-shot execute (scripting):
```bash
sac mcp execute sqlite insert_row --input '{"table":"users","row":{"name":"alice"}}' \
    --grant-id <grant-id>
```

### Tool Name Convention

All MCP tools are prefixed `mcp_<server>_<tool>` (dashes and dots replaced with `_`).
This guarantees they never shadow built-in tools (`read_file`, `edit_file`, etc.).

All surfaces in this section are EXPERIMENTAL and carry no stable contract.

## Cross-Session Project Memory (v6.2, EXPERIMENTAL)

SafeCode Agent remembers what happened in previous sessions and can learn
project-specific conventions over time.

### Session summaries

After every `sac ask`, `sac edit`, or `sac agent run` call, a bounded session
summary is automatically written to `.sac/memory/sessions.jsonl`. The next
session loads the last 3 summaries and prepends them to the agent's context.

```bash
sac memory inspect              # show recent session summaries
sac memory inspect --limit 10   # last 10 sessions
sac memory export               # print all summaries as JSON
sac memory export --out mem.json
```

### Project convention facts

During each session the agent infers conventions from what it observed — test
commands, lint commands, guarded directories — and proposes them as *pending*
facts. Pending facts are never injected into context until you explicitly
approve them.

```bash
sac memory list-facts            # all facts (pending + approved + rejected)
sac memory list-facts --pending  # awaiting your review
sac memory list-facts --approved # already active
sac memory approve-fact <id>     # approve a pending fact (audit-logged)
sac memory reject-fact <id>      # reject a pending fact
```

Approving a fact means it will appear in the "Approved Project Conventions"
section of the agent's context on every subsequent session.

From the interactive shell, `/memory review` shows the same pending facts in a
shorter review view. `/memory approve <id>` and `/memory reject <id>` accept the
short id shown by that view.

### Adding your own facts

```bash
# Propose a fact manually (it starts as pending; you still need to approve it)
sac memory list-facts --pending
sac memory approve-fact <id>
```

Or use `sac memory add-note` for free-form project notes (always visible,
no approval gate):

```bash
sac memory add-note "the /health endpoint must stay synchronous"
```

### Storage

| File | Purpose | Cap |
|---|---|---|
| `.sac/memory/sessions.jsonl` | Session summaries | 50 entries |
| `.sac/memory/facts.json` | Convention facts | 200 facts |
| `.sac/memory/project.md` | Free-form project notes | no cap |

All stored content is redacted with `redact_secrets()` before persistence.
Project-local files cannot create or approve facts.

All surfaces in this section are EXPERIMENTAL and carry no stable contract.

## Hybrid Context Retrieval (v6.3, EXPERIMENTAL)

SafeCode Agent v6.3 adds a hybrid retrieval pipeline combining keyword
path-matching, git recency, and semantic embedding similarity.

### Quick start

```bash
# Search without a semantic index (keyword + recency only — always works)
sac search "authentication flow"

# Enable semantic search (optional dependency)
pip install 'safecode-agent[semantic]'

# or with uv:
uv pip install 'safecode-agent[semantic]'

# Build a local embedding index for semantic search
sac index build

# Now search uses embedding similarity too
sac search "token expiry"
sac search "database retry logic" --limit 20
sac search "where is config loaded" --json
```

### selection_reason

Every search result shows why it was selected:

```
Score  File                        Reason
0.82   src/auth/session.py         path matched: auth; semantic (0.81)
0.61   src/middleware/jwt.py       semantic (0.61)
0.40   tests/test_auth.py          path matched: auth; recently modified
```

### Index management

```bash
sac index build          # incremental (only re-embeds changed files)
sac index build --force  # full rebuild
sac index status         # files, chunks, backend, last-built
sac index files          # list all indexed files
```

### Fallback behaviour

If `sentence-transformers` is not installed, the system uses `NullEmbeddingBackend`
and `semantic_score = 0` for all files. `sac search` still works using keyword
and recency signals only. Install `safecode-agent[semantic]` to unlock semantic search.

All surfaces in this section are EXPERIMENTAL and carry no stable contract.

## GitHub PR Workflow (v6.4, Stable Contract #20)

SafeCode Agent can push a branch and open a GitHub PR as part of the agent
loop. Two structural safety gates apply regardless of model output or config:

1. `main`, `master`, and `trunk` are always blocked from push — code-level.
2. The PR body always includes a SafeCode audit footer before any network call.

### Workflow

```bash
# Step 1: make your edits and apply them
sac edit "fix the auth timeout"
sac apply

# Step 2: preview the push (dry run — no network call)
sac shell
sac[1]> github_push_branch branch=feature/auth-fix dry_run=true
# Shows: [DRY RUN] Would push branch: feature/auth-fix to origin.

# Step 3: push the branch (requires approval)
sac[2]> github_push_branch branch=feature/auth-fix
# → approval gate → git push -u origin feature/auth-fix

# Step 4: preview the PR (dry run)
sac[3]> github_create_pr title="Fix auth timeout" body="Resolves session expiry." dry_run=true
# Shows the PR body with SafeCode audit footer

# Step 5: create the PR (requires approval)
sac[4]> github_create_pr title="Fix auth timeout" body="Resolves session expiry."
# → approval gate → gh pr create → returns PR URL
```

### PR body footer (always present)

Every PR created by SafeCode Agent includes:

```markdown
---
**SafeCode Audit Reference**
- Branch: `feature/auth-fix`
- Checkpoint: `2026-06-16T10-05-00Z_patch-abc123`
- Created: 2026-06-16T10:05:02+00:00
- Tool: SafeCode Agent `github_create_pr`
```

This lets reviewers trace the PR back to the exact checkpoint and audit event.

### Stable contract invariants

| Invariant | Guarantee |
|---|---|
| Protected branch block | `main`, `master`, `trunk` always rejected — structural |
| PR audit footer | Always appended — user sees it in approval preview |
| `dry_run=true` | No network call; always safe to run |
| `requires_approval` | Always true — cannot be disabled |
| Audit event types | `github_pr_created` / `github_branch_pushed` |

All surfaces in this section are part of **Stable Contract #20**.
