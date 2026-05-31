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

For local development:

```bash
uv sync
uv run sac --help
```

For a simple local tool install:

```bash
uv tool install .
sac doctor
```

For a complete first run, follow [docs/mvp-user-guide.md](docs/mvp-user-guide.md).

## Core Commands

```bash
sac ask "这个项目是什么？"
sac edit "给 FastAPI 项目添加 /health 接口"
sac apply
sac rollback --last
sac history
sac logs show --level error
sac config show
sac run "git status --short" --yes
sac doctor
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
