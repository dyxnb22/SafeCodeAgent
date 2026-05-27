# SafeCode Agent

SafeCode Agent is a safety-first Python terminal coding agent.

The v0.1 goal is not to build a full autonomous agent. The first goal is a small, reviewable code editing loop:

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

In v0.1, the LLM layer should use `MockLLMClient` first so the local workflow can be tested without real API keys.

## Planned CLI

```bash
sac ask "这个项目是什么？"
sac edit "给 FastAPI 项目添加 /health 接口"
sac apply
sac rollback --last
sac history
```

## Current Status

This repository currently contains the SafeCode Agent v0.1 framework. Implementation should continue in small reviewed steps.
