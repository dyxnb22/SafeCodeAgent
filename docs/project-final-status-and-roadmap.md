# SafeCode Agent Final Status and Roadmap

Status: current project baseline after `v4.12.3`.
Last updated: 2026-06-05.

This document is the consolidated product description for SafeCode Agent through
the v4.12 resume-ready MVP cut. The v4.10-v4.12 roadmap is now historical:
`docs/version-plans/v4.10-to-v4.12-resume-mvp-roadmap.md`. Forward work starts
after v4.12 and should not describe the DeepSeek, agentic-lite, or demo trains
as active planning items.

## Current Product Shape

SafeCode Agent is a safety-first Python terminal coding agent and local agent
runtime. Its strongest shipped capability is an auditable local edit/run loop:

```text
collect context
-> propose patch
-> preview diff
-> human approval
-> checkpoint
-> apply patch
-> validation
-> audit log
-> rollback
-> optional local commit
```

The resume-MVP front door is:

```sh
uv sync --extra examples
cd examples/fastapi-todo
pytest -q
../../examples/fastapi-todo/demo/run-demo.sh
```

The recorded transcript and tutorial are:

- `examples/fastapi-todo/demo/expected-transcript.md`
- `docs/tutorials/from-task-to-tested-commit.md`

All v4.10-v4.12 provider, agentic, validation, resume, smoke, demo, and example
surfaces remain EXPERIMENTAL. SafeCode still does not auto-apply, auto-commit,
push, create PRs, require an IDE, introduce RAG/embeddings, use LangGraph, or
run cloud/background tasks.

## Completed v4.10 DeepSeek Provider Train

v4.10 completed the real-provider reliability lane without changing the mock
default. It added the DeepSeek provider preset, `DEEPSEEK_API_KEY` resolution,
OpenAI-compatible endpoint normalization, setup wizard support, provider doctor
diagnostics that do not call the provider, retry/timeout behavior, and
credential-gated `sac smoke live-provider`.

The live-provider smoke remains opt-in and must not run unless
`SAFECODE_LIVE_SMOKE=1` and credentials are explicitly present.

## Completed v4.11 Agentic-Lite Loop Train

v4.11 evolved the existing `AgentLoop`; it did not introduce a new
`AgentTaskRunner`. The train added typed step/result projections, typed journal
events in the existing `AgentJournalStore`, `sac shell --agentic`,
`sac agent run`, read-only auto-approval boundaries, validation after apply-kind
steps, agentic resume, and deterministic mock-only `sac smoke agentic`.

Every mutating step remains approval-gated. Validation failures produce repair
proposals for review; they are not auto-applied.

## Completed v4.12 Demo and Resume-MVP Cut

v4.12 added the runnable FastAPI todo example, a deterministic mock transcript
demo, README front-door commands, a top-to-bottom tutorial, release notes,
matrix rows, threat-model coverage, and the `v4.12.3` release metadata cut.

The demo proves the MVP shape: task goal, plan, patch proposal, review
boundary, apply boundary, validation, and local commit prompt. The demo uses a
temporary working copy and never mutates the source example.

## Stable Runtime Still Preserved

- Config precedence and project-config lowering protection.
- Pending patch JSON format and diff preview.
- Checkpointed patch apply and rollback.
- Hash-chained audit log with anchor verification.
- Policy-gated command execution with high-risk command blocking.
- Dirty-tree guard for apply and local commit.
- Stable CLI JSON envelope and MCP read execution contracts from the v3.x/v4.0
  contract cuts.

## Important Limitations

- Live-provider coding quality depends on the configured provider and network
  policy.
- The demo is deterministic and mock-only; it is evidence of workflow shape,
  not evidence of live model quality.
- IDE/TUI product surfaces remain experimental or frozen; no IDE is required.
- No remote push/PR workflow exists in this release.
- RAG, embeddings, vector storage, LangGraph, hooks expansion, skills MVP, and
  broader language indexing are post-v4.12 future work.

## Post-v4.12 Forward Plan

Future work should be planned as a new post-v4.12 roadmap. Candidate areas:

- More realistic live-provider demo hardening while preserving opt-in gates.
- Better context ranking and explanation using local structured signals first.
- Optional hooks/skills extensions after the resume MVP remains stable.
- Broader language examples and deterministic smoke coverage.
- Developer experience polish for docs, install/update, and local-only support.

Any future train must keep the same safety invariants unless a separate public
contract process explicitly changes them.
