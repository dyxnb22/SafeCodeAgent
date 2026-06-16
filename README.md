# SafeCode Agent

**A safety-first Python terminal coding agent** — policy-gated command execution,
checkpointed file edits, rollback, audit logs, MCP tool integration, multi-provider
LLM support, context compaction, and a live evaluation harness.

The core loop never changes without your approval:

```text
collect context → propose patch → preview diff → human approval
    → checkpoint → apply patch → audit log → rollback
```

## Reproducible demo: from bug report to tested commit

Run the golden demo without live provider credentials (mock mode):

```bash
git clone <repo> && cd SafeCodeAgent
uv sync
examples/golden-demo/demo/run-demo.sh
```

Read the recorded transcript: [examples/golden-demo/demo/expected-transcript.md](examples/golden-demo/demo/expected-transcript.md)

See [docs/demo/portfolio-demo.md](docs/demo/portfolio-demo.md) for the full scenario,
commands, expected output, safety gates, and how to re-run.

## Install

**PyPI / pipx (recommended):**

```bash
pipx install safecode-agent
sac doctor
```

**Source dev:**

```bash
git clone <repo>
uv sync
uv run sac --help
sac doctor
```

**Offline wheel:**

```bash
uv build
pipx install dist/safecode_agent-*.whl
```

Homebrew tap: coming soon. See [docs/install-update.md](docs/install-update.md) for the full install matrix.

See [docs/install-update.md](docs/install-update.md) for the complete install matrix and release signing docs.

See [docs/README.md](docs/README.md) for the full documentation index.

Primary docs:
- [MVP User Guide](docs/mvp-user-guide.md) for a complete first run.
- [Install and Update](docs/install-update.md) for install, update, TestPyPI, signing, and release checks.
- [Public Contracts](docs/public-contracts.md), [Providers](docs/providers.md), and [Versioning Policy](docs/versioning-policy.md) for stable surfaces and configuration.
- [Current Status and Roadmap](docs/project-final-status-and-roadmap.md) for the current product baseline.
- [Why SafeCode](docs/why-safecode.md), [Comparison](docs/compare.md), [Troubleshooting](docs/troubleshooting.md), and [Context Budgets](docs/context-budgets.md) for product and operating references.

Historical release plans, audits, and version notes are indexed from [docs/README.md](docs/README.md).

**Per-stack tutorials**:
- [Python: First Hour](docs/tutorials/python-first-hour.md)
- [TypeScript: First Hour](docs/tutorials/typescript-first-hour.md)
- [Go: First Hour](docs/tutorials/go-first-hour.md)
- [AI Shell: First Hour](docs/tutorials/ai-shell-first-hour.md) — `sac shell` [EXPERIMENTAL v4.9]
- [Agent Run: First Hour](docs/tutorials/agent-run-first-hour.md) — `sac agent run` [EXPERIMENTAL v4.11-v4.12]

## Core Commands

**AI Shell (v4.9, EXPERIMENTAL):**
```bash
cd myproject && sac shell           # [EXPERIMENTAL] start the local AI shell
```
The shell accepts natural-language questions and slash commands (`/status`, `/overview`,
`/apply`, `/commit`, `/debug`, `/help`, `/exit`). All mutation paths require explicit
confirmation. No auto-apply. No auto-commit. No RAG or embeddings.
See [docs/tutorials/ai-shell-first-hour.md](docs/tutorials/ai-shell-first-hour.md).

**Trust Modes (v5.1, EXPERIMENTAL):**

| Mode | Command | What auto-approves | Still requires approval |
|---|---|---|---|
| `suggest` (default) | `sac shell` | Nothing — every edit/command prompts | All writes and commands |
| `auto-edit` | `sac shell --auto-edit` | `edit_file`, `write_file` | `run_command`, GitHub writes |
| `full-auto` | `sac shell --full-auto` | `edit_file`, `write_file`, `run_command` (within policy) | High-risk commands, GitHub writes |

All modes: checkpoints created before every write; `sac rollback --last` always undoes.
Full-auto prints a command preview and waits 500 ms (configurable via `--command-delay-ms`)
before executing — press Ctrl-C to abort a specific command. Cannot be persisted.

```bash
sac shell --auto-edit                        # auto-apply file edits; still prompt for commands
sac shell --full-auto                        # auto-apply edits AND commands (policy still gates)
sac shell --full-auto --command-delay-ms 0   # zero delay (for scripting/CI)
```

**Context Intelligence (v5.3, EXPERIMENTAL):**

SafeCode Agent now automatically pre-loads context relevant to your task:

- **Import-graph seeding:** when your task mentions a file (`edit src/auth/login.py`),
  SafeCode traces its first-degree imports and pre-loads up to 5 related files
  so the agent starts with the right context, not just keyword matches.
- **Git-aware context:** recent commits, files changed since your branch diverged
  from `main`, and high-churn files are injected into every session automatically.
- **Context compaction:** when accumulated tool results exceed 60% of the context
  budget, the model summarises what it has learned so far and archives the raw
  observations to `.sac/sessions/`. Long sessions no longer lose earlier context.

```
[Context compacted: ~3200 → ~600 tokens (12 observations archived)]
```

**MCP Integration (v5.4, EXPERIMENTAL):**

Add third-party MCP servers (e.g., `sqlite`, `brave-search`) in `.sac/mcp.toml`:

```toml
[servers.sqlite]
command = "uvx mcp-server-sqlite --db-path ./data.db"
scope = "read_only"       # or "write_proposal_required" to allow write tools
enabled = true
```

MCP read tools are bridged into the agent's native tool list automatically.
Tool names are prefixed `mcp_<server>_<tool>` to avoid collisions with built-ins.
Write tools (scope="write_proposal_required") require approval before execution.

```bash
sac mcp tools                         # list configured MCP tools from config
sac mcp list-native                   # list MCP tools registered with the agent [EXPERIMENTAL]
sac mcp call-readonly <srv> <tool>    # invoke a read-only MCP tool directly
sac mcp execute <srv> <tool> --grant-id <id>  # one-shot approved write (requires grant) [EXPERIMENTAL]
sac mcp doctor [server]               # check binary path, scope, lifecycle PID [EXPERIMENTAL]
sac mcp start <server>                # start a stdio MCP server process [EXPERIMENTAL]
sac mcp stop <server>                 # stop a stdio MCP server process [EXPERIMENTAL]
```

All MCP tool outputs pass through `redact_secrets()` before model context.
Write operations require an explicit approval grant — never auto-executed.

**Shell Display (v5.2, EXPERIMENTAL):**

The shell prompt shows turn count, task status, and cost estimate:
```
sac[3 · task:open · 2i · ~$0.02]>
```

Slash commands for display and tracking:
- `/cost` — session token count and estimated cost (`anthropic · claude-sonnet-4-6`)
- `/history` — recent turns with intent labels
- `/tools` — registered native tools with approval flags

Write-tool diffs show a compact header: `[+12 / -4 lines]  src/auth/login.py`

Long `run_command` output (>40 lines) is collapsed: first 5 + `--- [N lines hidden] ---` + last 5.

```bash
sac init                            # [v4.15+] guided first-run: provider, key, model, policy (recommended)
sac setup                           # first-time: write .sac/config.toml (hidden, still callable)
sac setup --wizard                  # interactive wizard: walks provider/model/policy (hidden)
sac quickstart                      # guided first-run: detects stack, shows demo, prints next steps
sac ask "这个项目是什么？"
sac edit "给 FastAPI 项目添加 /health 接口"
sac apply
sac rollback --last
sac commit                          # [EXPERIMENTAL] commit files touched by CURRENT task only
sac branch new <name>               # [EXPERIMENTAL] create/switch local branch without force/reset
sac diff --task                     # [EXPERIMENTAL] show applied + pending task changes
sac memory show                     # [EXPERIMENTAL] show redacted project memory
sac memory pin <path>               # [EXPERIMENTAL] keep a file considered for context
sac memory unpin <path>             # [EXPERIMENTAL] remove a pinned file
sac memory add-note "text"          # [EXPERIMENTAL] add a non-secret project/task note
sac memory clear --project --yes    # [EXPERIMENTAL] clear one memory scope
sac debug last-failure              # [EXPERIMENTAL] summarize the latest redacted failure
sac debug bundle --out bundle.tgz   # [EXPERIMENTAL] export redacted debug metadata, no source
sac audit query --task <task-id>    # [EXPERIMENTAL] read-only verified audit filtering
sac resume                          # [EXPERIMENTAL] recover an open/interrupted task safely
sac fix                             # run last failing test, propose a repair patch
sac fix --test-command "go test ./..."  # override test command
sac fix --watch                     # [EXPERIMENTAL] one approval-gated test-fix loop step
sac fix --watch --max-iterations 5  # [EXPERIMENTAL] cap proposals for the current task
sac fix --watch --rerun-suite all   # [EXPERIMENTAL] rerun profile suites through policy
sac fix --timeout-seconds 60        # [EXPERIMENTAL] override test/suite command timeout
sac run "git status --short" --yes
sac history                         # show recent audit events
sac history --task <task-id>        # [EXPERIMENTAL] filter by task id
sac doctor
sac version
```

**Local Git delivery (v4.5, EXPERIMENTAL):**
```bash
sac diff --task                     # read-only task diff; includes pending patch when present
sac commit --message-from-task      # local commit; stages only CURRENT task files
sac commit --include-task-summary   # include task iteration trail in the commit body
sac branch new fix/auth-regression  # create and switch to a new local branch
```

`sac apply` and `sac commit` include a dirty-tree guard. They refuse unrelated
tracked or staged changes by default, ignore untracked files outside touched
directories, and block untracked files inside touched directories. Use
`--allow-unrelated-changes` only when you have inspected those unrelated
changes. If a committed apply is later rolled back, `sac rollback --last`
refuses by default and suggests `git revert <sha>`; `--force-uncommit` is the
explicit dangerous opt-in. These v4.5 commands are local only and never push.

**Project memory (v4.6, EXPERIMENTAL):**
```bash
sac memory show
sac memory show --task --task-id <task-id>
sac memory show --recent-failures
sac memory show --pinned
sac memory pin src/app.py
sac memory unpin src/app.py
sac memory add-note "health route must stay synchronous"
sac memory clear --pinned --yes
```

Unified memory uses `.sac/memory/project.md`, `.sac/memory/recent-failures.jsonl`,
`.sac/memory/recent-edits.jsonl`, `.sac/memory/pinned-files.txt`, and
`.sac/tasks/<task_id>/memory.md`. Legacy `.sac/memory.json`, `.sac/progress.md`,
and `SAC.md` remain readable. Memory writes reject obvious secrets; CLI reads
are redacted. Pinned files are considered during context selection but still
consume a bounded context quota and never bypass ignore, sensitive-file, binary,
redaction, or project-root gates. Recent failures can help `sac fix` by adding
the newest three redacted failures as bounded task context.

**Observability commands (v4.19, EXPERIMENTAL):**
```bash
sac task stats                      # read-only summary of a task's iterations, budget, and pinned file count
sac task stats --task <task-id>     # stats for a specific task
sac task stats --json               # machine-readable JSON output
sac memory size                     # read-only .sac/ storage breakdown by scope (bytes + file count)
sac memory size --json              # machine-readable JSON output
```

Both commands are read-only and do not call the model, network, or shell. They
never mutate any file under `.sac/`. JSON output uses the stable `CLIJSONResponse`
envelope (contract 11).

**Agent Tool Calling (v4.20, EXPERIMENTAL):**
```bash
# The agent now calls read-only tools directly instead of packaging context up front.
# Tool calls are auto-approved, audited as tool_call_read events, and never write files.
# Available tools: read_file, list_files, search_files, grep_files
```

The native tool protocol lets the agent explore a codebase on demand: reading files
by path, listing directories, and searching for patterns — all within the project root,
with secret redaction applied to every result.

**Write and command tools (v4.21, EXPERIMENTAL):**
```bash
# edit_file — approval-gated exact string replacement with per-edit checkpoint
# write_file — approval-gated file create/overwrite with per-write checkpoint
# run_command — policy-gated shell command through ShellRunner (high-risk blocked)
```

Every `edit_file` and `write_file` call creates a checkpoint *before* the mutation —
the agent can make many edits and you can roll back any of them with `sac rollback --last`.
`run_command` passes through the same policy engine as `sac run`.

**GitHub tools (v4.24, EXPERIMENTAL):**

```bash
# Read tools (auto-approved, require network: true)
sac shell
sac> github_read_issue owner=acme repo=myapp issue=42
sac> github_read_pr    owner=acme repo=myapp pr=7
sac> github_read_file  owner=acme repo=myapp path=README.md ref=main
sac> web_fetch         url=https://docs.example.com/api

# Write tools (approval-gated, require network: true)
sac> github_create_pr  title="My PR" body="Fixes #42" base=main
sac> github_push_branch branch=dev/feature-x
```

Read tools use `gh` CLI with `shell=False` (no injection surface). Write tools
(`github_create_pr`, `github_push_branch`) are approval-gated — they pause
and show the command before executing. Auth via `GITHUB_TOKEN` env or
`gh auth status`. `web_fetch` strips scripts/style and caps at 50 KB.

**Anthropic / Claude as first-class provider (v4.23, EXPERIMENTAL):**

SafeCode now speaks the Anthropic native tool-use wire format. When using the
`anthropic` provider, the agent sends tool schemas as the Anthropic `tools`
parameter and receives structured `tool_use` blocks instead of freeform JSON.
OpenAI function calling is also wired for OpenAI-compatible providers.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
sac provider add anthropic --model claude-sonnet-4-6 --network
sac doctor --live   # now includes Anthropic API connectivity check (B16)
sac shell           # native tool use active for Claude
```

Key provider table (EXPERIMENTAL — not promoted to stable):

| Provider | Key env | Default model | Protocol |
|---|---|---|---|
| `mock` | — | `mock-model` | freeform JSON (default, deterministic) |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` | native tool use (v4.23) |
| `openai` | `OPENAI_API_KEY` | configured | function calling (v4.23) |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-v4-flash` | function calling via compat path |

**Multi-tool turns and shell UX (v4.22, EXPERIMENTAL):**
```bash
sac shell    # prompt now shows turn counter: sac[0]>  sac[1]>  ...
# New slash commands:
/undo        # roll back the most recent write-tool checkpoint
/history     # show recent turns for the current session
/tools       # list all available native tools
/clear       # now also resets the live agent session (not just display)
```

The agent can execute multiple tool calls per user message before generating
a final response — reading files, searching for patterns, and making edits
in a single turn.

**Debug commands (v4.7, EXPERIMENTAL):**
```bash
sac debug last-failure
sac debug last-failure --task <task-id> --json
sac debug bundle --out safecode-debug.tar.gz
sac debug bundle --task <task-id> --out safecode-debug.tar.gz --force
sac audit query --type shell_blocked --limit 20
sac audit query --task <task-id> --json
```

Debug surfaces are local and redacted. `last-failure` and `audit query` are
read-only. `debug bundle` writes a tar.gz containing SafeCode metadata only:
manifest, version/config/doctor snapshots, runtime logs, verified audit events,
task sidecars, project profile, and memory metadata. It excludes project source
code and refuses overwrite unless `--force` is set. All v4.7 debug surfaces are
EXPERIMENTAL and do not promote a stable contract.

**Task commands (v4.1, EXPERIMENTAL):**
```bash
sac task new "Fix auth regression"  # create a task and set it as current
sac task list                       # list all tasks
sac task show                       # show current task details
sac task switch <task-id>           # switch current task
sac task close                      # mark current task closed
sac task delete <task-id> --yes     # delete a task
sac status                          # show current task status and next recommended step
sac task budget show                # [EXPERIMENTAL] show per-task budget
sac task budget set --steps 8       # [EXPERIMENTAL] set per-task budget values
```

**Profile commands (v4.2, EXPERIMENTAL):**
```bash
sac profile detect                  # detect test/lint/typecheck/build commands for this project
sac profile show                    # show current profile
sac profile set test "pytest -q"    # override the test command
sac profile set lint "ruff check ." # override the lint command
sac profile clear test              # restore detected test command
sac run --suite test                # run the profile test command through policy
sac run --suite lint                # run the profile lint command through policy
sac run --suite typecheck           # run the profile typecheck command through policy
sac run --suite build               # run the profile build command through policy
```

**Fix watch loop (v4.3, EXPERIMENTAL):**
```bash
sac fix --watch                     # propose a pending patch, never auto-apply
sac apply                           # explicit approval step after reviewing the diff
sac fix --watch                     # rerun and either pass or propose the next pending patch
sac fix --watch --max-iterations 5
sac fix --watch --timeout-seconds 60
sac fix --watch --rerun-suite test
sac fix --watch --rerun-suite all
```

`sac fix --watch` is approval-gated: every patch proposal remains pending until
you explicitly run `sac apply`. All v4.3 fix-watch surfaces are EXPERIMENTAL.

**Resume and budgets (v4.4, EXPERIMENTAL):**
```bash
sac resume                          # make CURRENT resumable task active and print next step
sac resume <task-id>                # resume a specific open/interrupted task
sac task budget show
sac task budget set --steps 8 --time-seconds 600 --retries 2 --tokens 60000
```

`sac resume` never auto-runs `fix`, `edit`, `apply`, or a shell command. Ctrl-C
during `sac edit`, `sac fix`, `sac fix --watch`, or `sac run` marks the task
interrupted and prints `resume with: sac resume`. Budgets and stuck-loop
categories are experimental and do not change command policy or approval gates.

**Task-first daily loop (v4.x, EXPERIMENTAL):**

The v4.x shell-first flow links every command into one task-scoped session:

```bash
sac quickstart                      # detect stack, see demo, print next steps
sac task new "Add /health endpoint" # create task, set as CURRENT
sac profile detect                  # detect test/lint/typecheck/build commands
sac status                          # check CURRENT task state and next step
sac ask "explain the auth flow"     # read-only LLM question, no patch
sac edit "Add the /health endpoint" # propose patch, preview diff, await approval
# — or use the fix-watch loop —
sac fix --watch                     # run tests, propose repair patch on failure
sac apply                           # explicit approval: checkpoint + apply patch
sac commit --message-from-task      # local commit: CURRENT task files only
sac debug last-failure              # summarize last redacted failure, never executes
sac debug bundle --out debug.tgz    # redacted SafeCode metadata bundle, no source
```

Since v4.16.0, `sac --help` shows the 7 most-common daily commands (init, ask,
edit, apply, fix, commit, doctor). Run `sac help --all` to see the full callable
surface of 20+ commands including status, task, rollback, run, profile, resume,
memory, debug, shell, model, provider, version, and setup. All v4.x additions
remain EXPERIMENTAL. All trains through v4.18.2 are complete. No v5.0 release
is currently scheduled.

Use `--json` on most commands for machine-readable output:
```bash
sac fix --json
sac edit "task" --json
sac ask "question" --json
sac task list --json
sac status --json
sac resume --json
sac task budget show --json
```

## Safety Defaults

- File writes go through patch parsing, validation, diff preview, checkpoint, and audit log.
- High-risk shell commands are blocked even when `--yes` is passed.
- Shell commands run through argv execution, not a shell string.
- Shell, hooks, and read-only MCP execution go through command policy checks.
- Project config cannot lower user-level safety policy.
- Project hooks do not auto-approve medium-risk commands by default.
- Context collection skips secret-like filenames such as `.env.local`, `*token*`, `*secret*`, and key files.
- Network access is disabled by default.
- Network policy applies to shell commands and read-only MCP execution.
- Real LLM mode must pass network policy before any request is made.
- MCP write operations are disabled until an explicit proposal/approval policy exists.
- Approval stores and audit anchors live outside the project root.
- Audit events include trace ids for task reconstruction.
- Runtime errors are written to `.sac/logs/runtime.jsonl` for debugging.

## Policy Presets

SafeCode ships three canonical safety presets and two legacy aliases.

| Name | Type | Description |
|---|---|---|
| `strict` | canonical | Highest safety: minimal allowed commands, all confirmations required |
| `balanced` | canonical | Default balance: standard allowed commands, medium-risk confirmations |
| `experimental` | canonical | Wider allowed commands, fewer confirmations (local exploration) |
| `normal` | legacy alias | Identical to `balanced` |
| `learning` | legacy alias | Identical to `experimental` |

**Choosing a preset:**

Via `sac setup`:
```bash
sac setup --policy strict
sac setup --policy balanced
sac setup --policy experimental
```

Via `.sac/config.toml` (project config):
```toml
policy = "balanced"
```

Via environment variable:
```bash
export SAFECODE_POLICY=strict
```

**Safety invariants:**
- `block_high_risk` is `True` in every preset.
- `sandbox.restrict_to_project_root` is `True` in every preset.
- `network_enabled` is `False` in every preset.
- `SAFECODE_POLICY` can only raise effective policy, never lower it.
- An unknown `SAFECODE_POLICY` value issues a warning and is ignored.
- An unknown project config policy name cannot override a known user policy.
- Project config cannot lower user-level policy.

## Debug Runtime Logs

When a command fails, inspect recent runtime logs:

```bash
sac logs show --limit 20
sac logs show --level error --traceback
```

Runtime logs are structured JSONL events with component, level, message, error type, traceback, and extra details.

## Real LLM Mode

The default provider is `mock`, which keeps local tests deterministic.

To use an OpenAI-compatible provider:

```bash
sac model gpt-4.1-mini --provider openai --api-key sk-... --network
sac setup --yes --provider openai --model gpt-4.1-mini --network
sac ask "这个项目是什么？"
```

Model output is still parsed and validated by SafeCode before any write can happen.

Real LLM mode also requires trusted user-level and project-level network policy. A project-local config cannot enable network access by itself, and a project-local config cannot switch the model provider. Environment variables still take priority for temporary overrides.

See [docs/mvp-user-guide.md](docs/mvp-user-guide.md#model-configuration) for the exact config files.

### Real provider quickstart — provider profile UX (v4.14.0, EXPERIMENTAL)

Configure your provider once, then switch models by short alias:

```bash
sac provider add deepseek       # prompts for API key; writes trusted user config
sac model flash                 # use deepseek-v4-flash (daily default)
sac model pro                   # escalate to deepseek-v4-pro
sac --model deepseek:pro        # one-shot override for this invocation
sac model list                  # show available aliases for active provider
sac provider status             # show effective provider, model, credential source
sac doctor                      # static provider check, no network call
```

Inside `sac shell`:
```
sac> /model              # show current model and aliases
sac> /model flash        # switch (persisted globally)
sac> /provider status    # show provider profile status
```

### Real provider quickstart (DeepSeek, v4.10, EXPERIMENTAL)

```bash
sac model deepseek-v4-pro --provider deepseek --api-key sk-... --network
sac setup --wizard          # choose 'deepseek' at the provider prompt
sac doctor                  # verify provider key is detected (static check, no network call)
SAFECODE_LIVE_SMOKE=1 sac smoke live-provider   # opt-in round-trip smoke test
sac ask "What is 2+2?"
```

DeepSeek uses `https://api.deepseek.com` with the `deepseek-v4-flash` default model.
API key is read from `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `SAFECODE_LLM_API_KEY`, or the trusted user config written by `sac model` or `sac provider add`.
The `sac smoke live-provider` command requires `SAFECODE_LIVE_SMOKE=1` and refuses to run
without a valid key, a non-mock provider, and an enabled network policy.

## First Demo Task

Create and run a repeatable demo workflow:

```bash
sac demo materialize failing-test-repair
cd examples/demo-workflows/failing-test-repair
sac test run --yes
sac edit "Fix the calculator add function so the existing failing test passes."
sac apply
sac test run --yes
sac rollback --last
```

The same flow is documented with expected results in [docs/mvp-user-guide.md](docs/mvp-user-guide.md#first-task-failing-test-repair).

## Docker

Build:

```bash
docker build -t safecode-agent .
```

Run in the current workspace:

```bash
docker run --rm -it -v "$PWD:/workspace" -w /workspace safecode-agent sac doctor
```

## Test

```bash
PYTHONPATH=src python3 -m pytest -q
```

## Release Flow

For each release, keep the package version, runtime version, docs, and git tag
in lockstep:

```bash
sac release bump X.Y.Z
PYTHONPATH=src python3 -m pytest -q
git add -p
git commit -m "Implement vX.Y.Z <summary>"
git tag -a vX.Y.Z -m "vX.Y.Z <summary>"
sac release preflight          # aggregates check, smoke, metadata, docs, versions governance
sac release sync-versions-json # sync .claude/versions.json after tagging
git add .claude/versions.json
git commit -m "chore: sync versions.json to vX.Y.Z"
git tag -d vX.Y.Z && git tag -a vX.Y.Z -m "vX.Y.Z <summary>"  # move tag to sync commit
```

**TestPyPI rehearsal before production publish:**

```bash
sac release publish --repository test-pypi          # dry-run (no network)
SAFECODE_PUBLISH=1 sac release publish --no-dry-run --repository test-pypi
```

**Production publish:**

```bash
SAFECODE_PUBLISH=1 sac release publish --no-dry-run
```

Never tag a release while `pyproject.toml` or `safecode.__version__` still
reports an older version. `sac release preflight` is the final local gate.
See `docs/install-update.md` for signing and TestPyPI details.

## Roadmap

| Train | Versions | Theme | Status |
|---|---|---|---|
| v5.6.x | 3 | Agent quality: prompt engineering + live eval + golden demo | **Shipped** |
| v5.7.x | 3 | Security depth: threat model review + subagent activation + sandbox promotion | **Shipped** |
| v5.8.x | 3 | Cost guardrails + v6.0 contract preparation | **Shipped** |
| **v6.0.0** | 1 | **Major contract cut** — trust modes, session rollback, cost cap promoted to stable. Zero v5.0 breaking changes. | **Next** |

See [docs/version-plans/v5.6-to-v5.8-product-roadmap.md](docs/version-plans/v5.6-to-v5.8-product-roadmap.md)
for the full plan. See [docs/v6-contract-candidates.md](docs/v6-contract-candidates.md)
for v6.0 candidate surfaces.

## IDE and TUI Status (v3.9.x)

**VS Code Extension (experimental):**
- Source: `vscode-extension/` — TypeScript, spawns `sac api jsonrpc` over stdio.
- Approval prompt is a VS Code modal. No telemetry. No marketplace publish in v3.9.x.
- VSIX build requires Node.js + npm install + `npm run build` (tsc); see `docs/version-notes/v3.9.2-vscode-tui.md`.

**TUI (`sac tui interactive`, experimental, frozen at v3.5.2):**
- Rich-based; deterministic non-TTY static snapshot; Ctrl-C exits in TTY.
- Frozen at v3.5.2 behavior. No Textual upgrade planned before v4.0 re-audit.
- Do not rely on TUI output format for automation; surface is explicitly experimental.
