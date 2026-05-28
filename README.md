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

## Core Commands

```bash
sac ask "这个项目是什么？"
sac edit "给 FastAPI 项目添加 /health 接口"
sac apply
sac rollback --last
sac history
sac config show
sac run "git status --short" --yes
sac doctor
```

## Safety Defaults

- File writes go through patch parsing, validation, diff preview, checkpoint, and audit log.
- High-risk shell commands are blocked even when `--yes` is passed.
- Shell commands run through argv execution, not a shell string.
- Project config cannot lower user-level safety policy.
- Network access is disabled by default.
- MCP write operations are disabled until an explicit policy exists.

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

