# SafeCode Agent

SafeCode Agent is a safety-first Python terminal coding agent and local agent runtime.

It is designed around a controlled loop:

```text
collect context
-> propose patch
-> preview diff
-> human approval
-> checkpoint
-> apply patch
-> audit log
-> rollback
```

## Install

**Local development (primary):**

```bash
git clone <repo>
uv sync
uv run sac --help
sac doctor
```

**pipx (once available on PyPI):**

```bash
pipx install safecode-agent
```

**TestPyPI rehearsal install:**

```bash
pipx install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  safecode-agent
```

**Offline wheel (build locally):**

```bash
uv build
pipx install dist/safecode_agent-*.whl
```

See `docs/install-update.md` for the full install, update, and release signing guide.

For a complete first run, follow [docs/mvp-user-guide.md](docs/mvp-user-guide.md).

For stable local safety contracts (v3.0), see [docs/public-contracts.md](docs/public-contracts.md).
For LLM provider configuration and contract details, see [docs/providers.md](docs/providers.md).
For release versioning semantics and the v4.0 contract churn budget, see [docs/versioning-policy.md](docs/versioning-policy.md).
For the post-v3.0 commercial product architecture reference, see
[docs/product-commercialization-roadmap.md](docs/product-commercialization-roadmap.md).
For the active post-v4.0.0 shell-first execution plan, see
[docs/version-plans/v4.1-to-v4.8-shell-first-roadmap.md](docs/version-plans/v4.1-to-v4.8-shell-first-roadmap.md).
The previous v3.7→v4.0 plan is preserved at
[docs/version-plans/v3.7-to-v4.0-product-roadmap.md](docs/version-plans/v3.7-to-v4.0-product-roadmap.md);
the v4.0 readiness audit is
[docs/commercial-v1-readiness-audit-v3.11.x.md](docs/commercial-v1-readiness-audit-v3.11.x.md).
For why SafeCode, see [docs/why-safecode.md](docs/why-safecode.md).
For a comparison with other approaches, see [docs/compare.md](docs/compare.md).
For troubleshooting help, see [docs/troubleshooting.md](docs/troubleshooting.md).
For context budget configuration, see [docs/context-budgets.md](docs/context-budgets.md).

**Per-stack tutorials**:
- [Python: First Hour](docs/tutorials/python-first-hour.md)
- [TypeScript: First Hour](docs/tutorials/typescript-first-hour.md)
- [Go: First Hour](docs/tutorials/go-first-hour.md)

## Core Commands

```bash
sac setup                           # first-time: write .sac/config.toml
sac setup --wizard                  # interactive wizard: walks provider/model/policy (non-TTY prints template)
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

The root CLI surface is trimmed to 17 visible daily-loop commands: `setup`,
`quickstart`, `status`, `task`, `ask`, `edit`, `fix`, `apply`, `rollback`,
`run`, `commit`, `profile`, `resume`, `memory`, `debug`, `doctor`, `version`.
All v4.x additions remain EXPERIMENTAL. The v4.x shell-first train is complete
as of v4.8.2. No v5.0 release is currently scheduled.

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
export SAFECODE_LLM_PROVIDER=openai
export SAFECODE_LLM_MODEL=gpt-4.1-mini
export OPENAI_API_KEY=...
uv run sac ask "这个项目是什么？"
```

Model output is still parsed and validated by SafeCode before any write can happen.

Real LLM mode also requires trusted user-level and project-level network policy. A project-local config cannot enable network access by itself, and a project-local config cannot switch the model provider.

See [docs/mvp-user-guide.md](docs/mvp-user-guide.md#model-configuration) for the exact config files.

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

## IDE and TUI Status (v3.9.x)

**VS Code Extension (experimental):**
- Source: `vscode-extension/` — TypeScript, spawns `sac api jsonrpc` over stdio.
- Approval prompt is a VS Code modal. No telemetry. No marketplace publish in v3.9.x.
- VSIX build requires Node.js + npm install + `npm run build` (tsc); see `docs/version-notes/v3.9.2-vscode-tui.md`.

**TUI (`sac tui interactive`, experimental, frozen at v3.5.2):**
- Rich-based; deterministic non-TTY static snapshot; Ctrl-C exits in TTY.
- Frozen at v3.5.2 behavior. No Textual upgrade planned before v4.0 re-audit.
- Do not rely on TUI output format for automation; surface is explicitly experimental.
