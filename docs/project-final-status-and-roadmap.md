# SafeCode Agent Final Status and Roadmap

**Status:** current project baseline after `v7.1.5`.
**Last updated:** 2026-06-17.

> **Update (2026-06-17, v7.1.5):** v7.0.x productization and v7.1 eval maturity
> are complete. Package/runtime metadata now point at v7.1.5. The default live
> suite has 38 fixtures, `sac agent run` has a single-command happy path,
> read-only subagent roles are productized, session/shell timeline polish is in
> place, and eval reports can be summarized with `sac eval --mode dashboard`.
> No new stable contract was added after the v7.0.0 contract cut.

> **Forward plan:** v7.0.x and v7.1.x are now closed. Future work should start
> from the eval dashboard and version-note ledger, then open a new version plan
> rather than extending the completed v7.0.x follow-up plan.

> **Update (2026-06-16, v6.1.0):** Portfolio maturity cut complete. The
> project now has a redacted real DeepSeek `deepseek-v4-flash` live eval result,
> a more realistic multi-file demo, project hook stages (`before_command`,
> `after_edit`, `after_test`, `after_apply`), and diagnostics-aware context
> collection for bounded pytest/tsc/go feedback before patch proposal.
>
> **Update (2026-06-16, v6.0.0):** v6.0.0 is the second major contract cut
> after v5.0.0. Trust mode schema and session rollback are now stable contracts
> (sections 18-19 of public-contracts.md). Zero v5.0 breaking changes. Cost
> guardrails remain experimental until they have release-cycle evidence.
>
> **Update (2026-06-16, v5.8.2):** The v5.6.x agent quality train (prompt engineering,
> live eval, golden demo) and v5.7.x security depth train (threat model review,
> subagent activation, sandbox contract promotion) and v5.8.x cost/v6-prep train
> are complete.
>
> See [docs/v6-contract-candidates.md](v6-contract-candidates.md) for the v6.0
> candidate assessment. See [archive/version-plans/v5.6-to-v5.8-product-roadmap.md](archive/version-plans/v5.6-to-v5.8-product-roadmap.md) for the complete train plan.
>
> **v7.1.5 is the current product baseline; v7.0.0 remains the current stable-contract cut.** Terminal-only tool by
> design. 23 stable contracts (sections 1-23 of public-contracts.md). Cost
> guardrails, live eval, and golden demo were added in v5.6-v5.8; trust modes
> and session rollback were promoted in v6.0.0. v6.1.0 adds portfolio-grade
> evidence and developer workflow depth without adding new stable contracts.

---

## v6.1.0 Product Baseline (2026-06-16)

SafeCode Agent v7.1.5 is the current product baseline. PyPI (pipx) is the
production install path. MCP tool bridge, trust modes, session rollback, cost
guardrails, diagnostics-aware context, project hooks, and 23 stable contracts
are complete. Cost guardrails, diagnostics context, and project hooks remain
experimental; trust modes and session rollback are stable.

### Portfolio Evidence

| Evidence | Status |
|---|---|
| Golden demo: bug report -> diff preview -> tests pass | ✅ `examples/golden-demo/` |
| Realistic multi-file service demo | ✅ `examples/realistic-demo/` |
| Real provider live eval | ✅ DeepSeek `deepseek-v4-flash`, 2/2 fixtures passed |
| Redacted live eval artifact | ✅ `docs/demo/live-eval-summary.md`, `tests/snapshots/live_eval/latest.json` |
| Hooks MVP | ✅ `before_command`, `after_edit`, `after_test`, `after_apply` |
| Diagnostics-aware context | ✅ bounded pytest/tsc/go collection before edit proposals |

### Distribution

| Method | Command | Status |
|---|---|---|
| PyPI (recommended) | `pipx install safecode-agent` | ✅ v5.5.0+ |
| Source dev | `git clone … && uv sync` | ✅ always |
| Offline wheel | `uv build && pipx install dist/<wheel>` | ✅ always |

### v6.0.0 Promotions

| Surface | Status |
|---|---|
| Trust mode schema (`suggest`, `auto-edit`, `full-auto`) | ✅ Stable (Section 18) |
| `sac rollback --session <id>` | ✅ Stable (Section 19) |
| `cost.max_tokens_per_session` | Deferred; remains experimental |
| MCP native tool bridge schema | Deferred; remains experimental |

### MCP Integration (v5.4)

| Feature | Status |
|---|---|
| Native tool bridge (MCP → NativeToolSpec) | ✅ EXPERIMENTAL (v5.4.0) |
| Write execution flow (approve → grant → execute) | ✅ EXPERIMENTAL (v5.4.1) |
| `sac mcp list-native` | ✅ EXPERIMENTAL (v5.4.0) |
| `sac mcp execute --grant-id` | ✅ EXPERIMENTAL (v5.4.1) |

---

## v5.3.2 Complete Product Baseline (2026-06-15)

SafeCode Agent v5.3.2 delivers terminal experience parity with Claude Code and
Codex CLI across all major dimensions:

### Core capabilities

| Capability | Status | Version |
|---|---|---|
| Native tool calling (read/write/command) | ✅ Stable contracts | v5.0.0 |
| Multi-tool turns (20-tool cap) | ✅ | v4.22.0 |
| Anthropic + OpenAI provider support | ✅ | v4.23.0 |
| Trust modes (auto-edit, full-auto) | ✅ EXPERIMENTAL | v5.1.x |
| Prompt caching (Anthropic) | ✅ EXPERIMENTAL | v5.1.0 |
| Session cost tracking (/cost) | ✅ EXPERIMENTAL | v5.2.0 |
| Import-graph context seeding | ✅ EXPERIMENTAL | v5.3.0 |
| Git-aware context | ✅ EXPERIMENTAL | v5.3.0 |
| Context compaction (60% threshold) | ✅ EXPERIMENTAL | v5.3.1 |

### Safety infrastructure (all stable)

| Feature | Status |
|---|---|
| Checkpoint before every write | ✅ Stable contract |
| Rollback by checkpoint / session | ✅ Stable contract |
| Hash-chained audit log | ✅ Stable contract |
| Policy-gated command execution | ✅ Stable contract |
| Project-config cannot weaken user policy | ✅ Stable invariant |
| B-series reliability bugs (B1–B17) | ✅ All closed |

### All B-series reliability bugs closed

| Bug | Fix version | Description |
|---|---|---|
| B1 | v4.23.0 | Empty choices[] in OpenAI response |
| B2 | v4.23.0 | Empty content blocks in Anthropic response |
| B3 | v4.23.0 | Stream timeout (per-chunk 30s) |
| B4 | v4.20.0 | Path traversal in read_file |
| B5 | v4.20.0 | File tree truncation not signalled |
| B6 | v4.21.0 | edit_file multi-match not detected |
| B7 | v4.21.0 | write_file disk-full error |
| B8 | v4.21.0 | max_steps too low (5→20) |
| B9 | v4.22.0 | Stuck loop detection outside task scope |
| B10 | v4.22.0 | /clear not resetting AgentSessionStore |
| B11 | v4.22.0 | EOF handling non-consistent TTY/non-TTY |
| B12 | v4.23.0 | URL in retry log messages |
| B13 | v4.25.0 | Checkpoint no sha256 |
| B14 | v4.25.1 | Doctor no disk check |
| B15 | v4.25.1 | Init no connectivity check |
| B16 | v4.23.0 | Doctor no Anthropic API check |
| B17 | v4.20.0 | Sensitive path bypass in list_files |

### Explicitly deferred post-v5.3

| Item | Reason |
|---|---|
| **Computer use / screenshot input** | Requires multimodal model + screen permission model |
| **IDE integration** | SafeCode is a terminal tool by design |
| **RAG / embeddings / vector search** | High complexity; import graph + git context covers the common case |
| **Multi-repo context** | Requires cross-repo path validation redesign |
| **Remote / background agents** | Requires server infrastructure |
| **Anthropic MCP server** | Reverses client direction; separate product |

The v4.14–v4.18 usability trains are historical and complete. Both the post-v4.14
usability roadmap (8 versions) and the post-v4.16 shell UX roadmap (6 versions)
shipped fully. The current product baseline is v6.1.0; older v4.x freeze notes
below are retained only for release archaeology.

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

## Completed v4.19.x Local Observability Polish Train

The v4.19.x local observability train is COMPLETED as of v4.19.2 on the `dev/v4.19`
branch. All 3 versions shipped:

- **v4.19.0**: `sac task stats [--task <id>] [--json]` — read-only per-task
  iteration histogram, budget, and pinned file count; 16 tests.
- **v4.19.1**: `sac memory size [--json]` — read-only `.sac/` byte/file breakdown
  by named scope (audit/checkpoints/memory/runtime_logs/tasks/other); 12 tests.
- **v4.19.2**: docs cut — README observability section, MVP guide "Inspecting Local
  State" section, troubleshooting "Reading local state" entry, matrix rows,
  docs guard tests, SKILL.md/versions.json/final-status updates.

Both commands are pure read-only: no model, network, or shell; no mutation.
All surfaces remain EXPERIMENTAL. No stable contract promoted.

## Historical Freeze Note

`main` is frozen at `v4.18.2` as a learning baseline and portfolio reference.
The `dev/v4.19` branch baseline is now `v4.19.2`.

This section is historical. The current documented baseline is v7.1.5. Remaining
out-of-scope work (RAG, embeddings, LangGraph, IDE surface, remote push/PR, and
agent hooks expansion) remains deferred unless a new roadmap explicitly adopts it.
