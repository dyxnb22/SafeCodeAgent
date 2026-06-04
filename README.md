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
For the active post-v3.6.6 execution plan, see
[docs/version-plans/v3.7-to-v4.0-product-roadmap.md](docs/version-plans/v3.7-to-v4.0-product-roadmap.md)
and the readiness audit
[docs/commercial-v1-readiness-audit-v3.6.6.md](docs/commercial-v1-readiness-audit-v3.6.6.md).
For why SafeCode, see [docs/why-safecode.md](docs/why-safecode.md).
For a comparison with other approaches, see [docs/compare.md](docs/compare.md).
For troubleshooting help, see [docs/troubleshooting.md](docs/troubleshooting.md).
For context budget configuration, see [docs/context-budgets.md](docs/context-budgets.md).

**Per-stack tutorials**:
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
sac fix                             # run last failing test, propose a repair patch
sac fix --test-command "go test ./..."  # override test command
sac run "git status --short" --yes
sac doctor
sac version
```

Use `--json` on most commands for machine-readable output:
```bash
sac fix --json
sac edit "task" --json
sac ask "question" --json
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
