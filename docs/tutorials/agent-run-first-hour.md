# Agent Run: First Hour

`sac agent run` is EXPERIMENTAL. It uses the existing `AgentLoop`, journal, validation loop, pending-patch review, apply checkpoint, and local commit primitives. It does not introduce auto-apply, auto-commit, push, PR creation, IDE requirements, RAG, embeddings, or background cloud work.

## 1. Start With The Mock Demo

The fastest first hour uses the bundled FastAPI todo example and needs no live provider credentials:

```bash
uv sync --extra examples
cd examples/fastapi-todo
pytest -q
../../examples/fastapi-todo/demo/run-demo.sh
sac demo agent-loop
PYTHONPATH=src pytest -q
```

Compare the output with `examples/fastapi-todo/demo/expected-transcript.md`. The transcript shows the agent-shaped flow: task goal, plan, patch proposal, review boundary, apply boundary, validation, and commit prompt. The script uses a temporary working copy and removes it when done.

## 2. Run The Real Command On A Local Project

Inside your own project, set up SafeCode and detect the profile:

```bash
sac quickstart
sac task new "add input validation to the registration endpoint"
sac profile detect
sac status
```

Ask a read-only question before asking for a change:

```bash
sac ask "where is registration handled?"
```

Then run the EXPERIMENTAL agent:

```bash
sac agent run "add input validation to the registration endpoint"
```

The agent plans, collects context, proposes a patch, and stops at approval-required steps. In non-TTY mode, mutating approvals fail closed.

## 3. Review, Apply, Validate

Preview the pending diff first:

```bash
sac apply --preview
sac apply
sac run --suite test
```

After apply-kind steps, the validation loop runs the configured profile test suite first, then lint, typecheck, and build where those commands exist. A failing validation records a redacted failure tail and proposes a repair patch for review; it is still never auto-applied.

## 4. Recover Or Finish Locally

Use the existing recovery and local delivery commands:

```bash
sac resume
sac debug last-failure
sac diff --task
sac commit --message-from-task
```

`sac commit` is local only and stages files SafeCode can associate with the current task. There is no remote push command in this workflow, no PR automation, and no hidden remote publish step.

## Safety Summary

- No live provider is required for the demo; it is mock-only.
- Live providers such as DeepSeek are optional and still EXPERIMENTAL in the v4.10-v4.12 train.
- No auto-apply and no auto-commit: you approve apply and commit separately.
- No IDE is required.
- All v4.10-v4.12 agent/demo/provider surfaces remain EXPERIMENTAL and promote no new stable contracts.
