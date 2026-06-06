# SafeCode Agent Final Status and Roadmap

Status: current project baseline after `v4.18.2` (pre-freeze).
Last updated: 2026-06-06.

This document is the consolidated product description for SafeCode Agent through
the v4.14–v4.18 usability trains. Both the post-v4.14 usability roadmap (8 versions)
and the post-v4.16 shell UX roadmap (6 versions) are COMPLETED. 14 versions shipped
across both trains. The v4.10-v4.12 roadmap and post-v4.12 consolidation plan are
historical. No active forward plan at this time.

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
The follow-up `v4.12.4` repository hotfix tracks the FastAPI todo
`.sac/project_profile.json` required for clean-clone demo validation; it does
not promote new behavior or stable contracts.

The demo proves the MVP shape: task goal, plan, patch proposal, review
boundary, apply boundary, validation, and local commit prompt. The demo uses a
temporary working copy and never mutates the source example.

## Completed v4.14–v4.16 Usability Train

The post-v4.14 usability roadmap is complete (8 versions, all shipped and
tagged). Key deliverables:

- **v4.14.0**: provider-profile UX (`sac provider add`, model aliases, one-shot `--model`)
- **v4.14.1**: diagnostic clarity (doctor/provider status verdicts, next-command hints)
- **v4.14.2**: `--model` parity on ask/edit/fix/run/agent-run subcommands
- **v4.15.0**: `sac init` as the single guided first-run front door
- **v4.15.1**: session-scoped model switching (`--save` for persistence)
- **v4.15.2**: keychain/env-only credentials (`--store` flag, keyring backend)
- **v4.16.0**: bare `sac` enters shell, 7-command daily help surface, `sac help --all`
- **v4.16.1**: config migration (`sac config migrate`, legacy `[llm]` → `[providers]`)
- **v4.16.2**: error-message rewrite (`FailureCategory.next_command`, `sac why`)

All v4 surfaces remain EXPERIMENTAL and promote no new stable contracts.
Project-local config still cannot store credentials or silently widen
user-level network policy.

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
- Interaction-quality gaps from before v4.17 (no streaming, basic shell UX, no live
  connectivity checks, no fuzzy matching, no per-patch undo) are all addressed in the
  v4.17–v4.18 train. See below.

## Completed v4.17–v4.18 Shell & Interaction UX Train

The post-v4.16 shell UX roadmap is COMPLETED as of v4.18.2. All 6 versions shipped:

- **v4.17.0**: streaming token-by-token output in `sac ask` and `sac shell`
- **v4.17.1**: shell polish (Rich Markdown, diff highlighting, readline completer, `/clear`)
- **v4.17.2**: live connectivity diagnostics (`sac doctor --live`, `sac provider status --live`)
- **v4.17.3**: Levenshtein fuzzy matching for model/provider names
- **v4.18.0**: per-patch undo (`sac rollback --checkpoint <id>`, `--list`) + shell diff rendering
- **v4.18.1**: agent-loop transparency (Rich Status spinner, on_step callback)
- **v4.18.2**: safety regression fix — `--checkpoint <id>` rollback path was missing
  `ToolCallGate` check; corrected and covered by 5 new tests.

All surfaces remain EXPERIMENTAL. No safety invariants changed.

## Current Freeze Goal

`main` is frozen at `v4.18.2` as a learning baseline and portfolio reference.
Future feature development will continue on a separate development branch.

No active forward plan at this time. Remaining work (RAG, embeddings, LangGraph,
IDE surface, remote push/PR, agent hooks expansion) is deferred to that future
branch and is NOT part of the current baseline.
