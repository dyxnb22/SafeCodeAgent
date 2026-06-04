# SafeCode Agent Product Commercialization Roadmap (post-v3.0.0)

Status: planning. No runtime behavior change in this pass.
Baseline: tag `v3.0.0`, package version `3.0.0`, regression `2398 passed, 9 warnings`,
`sac release preflight` clean.
Authoring date: 2026-06-02.

Planning update, 2026-06-03: this document remains the architecture reference
and record of commercial-product intent. The active execution plan after the
v3.6.6 documentation cut is
`docs/version-plans/v3.7-to-v4.0-product-roadmap.md`, with the current
readiness baseline in `docs/commercial-v1-readiness-audit-v3.6.6.md`.

Planning update, 2026-06-04: the v3.7-to-v4.0 execution plan closed at the
v4.0.0 contract cut. This document remains the commercial architecture
reference, but the active forward execution plan is now
`docs/version-plans/v4.1-to-v4.8-shell-first-roadmap.md`, scoped to
shell-first functional completeness rather than commercialization. The
current readiness baseline is
`docs/commercial-v1-readiness-audit-v3.11.x.md`.

Planning update, 2026-06-04: the v4.1-to-v4.8 shell-first train closed at
v4.8.2. The active forward execution plan is now
`docs/version-plans/v4.9-ai-shell-mvp-roadmap.md`, scoped to a Claude
Code-like local AI shell around existing SafeCode primitives. RAG, embeddings,
vector storage, LangGraph, stable contract promotion, and v5 scheduling are
out of scope for v4.9.

Planning update, 2026-06-04: the v4.9 AI shell train closed at v4.9.3. The
current consolidated product status and forward plan is
`docs/project-final-status-and-roadmap.md`. The v4.9 plan remains as a
completed implementation record.

This roadmap analyzes SafeCode Agent as a commercial-grade local coding agent
product, not merely as a local safety runtime. It identifies what is solid,
what is incomplete, what is experimental, what architecture needs refinement,
and what tasks should be planned next. Sources read while writing:
`README.md`, `docs/public-contracts.md`, `docs/version_implementation_matrix.md`,
`docs/version-plans/v2.8-to-v3.0-product-architecture-roadmap.md`,
`.claude/versions.json`, `.claude/skills/current/SKILL.md`, `pyproject.toml`,
the full `src/safecode/` tree, and the `tests/` taxonomy (96 test files,
including snapshots, contracts, eval, sandbox, mcp, subagent, agent-loop,
release, and tools tests).

---

## 1. Executive Summary

### What has landed by v3.0.0

By v3.0.0 SafeCode Agent ships a **stable local safety runtime** with eight
documented public contracts and six surfaces explicitly labeled experimental.
The shipped substrate, distilled from `docs/public-contracts.md` and snapshot
coverage in `tests/test_public_contract_snapshots.py` /
`tests/test_tool_schema_registry.py`, is:

1. **Config precedence and lowering rules** — `SafeCodeConfig`, three canonical
   presets (`strict`, `balanced`, `experimental`), two legacy aliases, env-var
   warning behavior, project-config cannot lower user-level safety.
2. **Pending patch format** — `PatchProposal`/`PatchBlock` JSON with stable
   field set; `status` ∈ {pending, applied, rejected}.
3. **Audit event hash-chain** — append-only JSONL with `event_hash` +
   `previous_hash`, anchor store living outside the project root, integrity
   failure on log-without-anchor.
4. **Sandbox lifecycle** — `propose → preflight → approve (single-use,
   atomic, project-bound, outside project root) → execute → result_record`,
   shared across Noop/Docker/Seatbelt/Bubblewrap planners.
5. **Local tool registry shape** — `ToolSpec.version`, frozen registry
   schema version (`REGISTRY_SCHEMA_VERSION = "1"`), 17 registered tools,
   invariants tying high-risk and WRITE/SHELL tools to human approval.
6. **Deterministic eval trace** — `LoopStepTrace`/`LoopEvalTrace`
   serialisable from the fixture definition alone, byte-stable, six default
   fixtures.
7. **Recommended CLI workflow** — daily-use commands surfaced in
   `sac --help`; release surface collapsed to `preflight`, `bump`, `changelog`.
8. **Hidden/internal release policy** — `signoff`/`checklist`/`check`/`smoke`/
   `meta` remain callable but hidden, `signoff` emits a deprecation
   `RuntimeWarning`.

Experimental, explicitly NOT frozen at v3.0: `SafeCodeLocalAPI` beyond
`ask()`/`report()`, OpenAI-compatible live provider behavior, the MCP schema
shim, subagent payload evolution beyond v1 read-only findings, `sac tui`,
`sac ide`.

### Is the product usable today?

Yes, for a narrow set of use cases.

- **Solid use case A — auditable local patch loop:** propose → preview →
  approve → checkpoint → apply → audit → rollback works end-to-end against
  the bundled `mock` LLM and any OpenAI-compatible endpoint when network
  policy is explicitly enabled. The diff/apply/rollback path is the most
  battle-tested area of the codebase.
- **Solid use case B — policy-gated shell execution:** `sac run` classifies
  commands, blocks high-risk operations even under `--yes`, runs through
  argv execution (not a shell string), respects project-config lowering
  rules, and now (since v2.8.8) returns honest exit codes (`125`
  approval-required, `126` policy-blocked).
- **Solid use case C — sandbox dry-run/proposal infrastructure:**
  approvals are single-use, atomic, project-bound, with full security
  evals across Noop, Docker, Seatbelt, and Bubblewrap planners.
- **Solid use case D — scripted/replay evaluation:** `sac eval --mode loop`
  is deterministic, six fixtures, snapshot-tested, and gated in CI (advisory).

### Where the product is **not yet** a commercial-grade coding agent

- **Real LLM reliability is unproven at scale.** `OpenAICompatibleLLMClient`
  is 126 LOC, synchronous `urllib`, no retry, no token accounting, no
  streaming, no structured-output validation beyond the agent contract
  parser, no provider fan-out (Anthropic, Bedrock, local Ollama/vLLM).
- **No multi-turn task memory beyond a single journal session.** The
  loop is a single goal → plan → step → approve loop; there is no project-
  level memory store the agent reads on subsequent sessions.
- **Repo intelligence is rudimentary.** `FileIndexer`,
  `PythonSymbolIndex`, and `RepoMap` exist but ranking is shallow and there
  is no semantic / embedding fallback.
- **No real MCP JSON-RPC client.** All MCP integration is static schema
  + classification shim. Real read calls and proposal/approval-gated writes
  are stubs.
- **No subagent concurrency or LLM-driven synthesis.** The subagent
  dispatcher is file-based, read-only, single-task; the merge surface
  redacts and bounds findings but does not orchestrate parallel fan-out.
- **No IDE plug-in, no real TUI.** `sac ide` writes a pending diff file
  and prints `IDEOpenTarget` URIs. `sac tui dashboard` renders a Rich
  panel — it is not interactive.
- **No install/update channel beyond `pip` / `uv tool install .`.**
  No signed releases, no auto-update, no telemetry-opt-in path.
- **No multi-project, no team trust, no policy server.** All trust roots
  are file-based.

### One-line product framing

> v3.0.0 is a *stable, auditable local safety substrate for a coding agent*.
> The commercial product layer — provider reliability, real coding UX,
> multi-turn memory, IDE/TUI surfaces, real MCP execution, subagent
> orchestration, packaging, and support — has not yet shipped.

---

## 2. Current Architecture Analysis

For each area: strengths, gaps, risk level (Low/Med/High in terms of
*commercialization* risk if shipped as-is), recommended direction.

### 2.1 CLI / runtime architecture

**Where:** `src/safecode/cli.py`, `cli_core.py`, `cli_agent.py`, `cli_ops.py`,
`cli_quickstart.py`, `cli_sandbox*.py`, `cli_mcp.py`, `cli_subagent.py`,
`cli_test_demo.py`, `cli_project.py`, `cli_tui.py`, `cli_context.py`.

- **Strengths:** Typer-based, root help trimmed (v2.7.6), release surface
  collapsed (v2.8.5), sandbox CLI split (v2.8.6). Daily-use commands are
  small, deterministic, and exit codes are honest (v2.8.8). Quickstart
  command exists. `sac doctor` runs release-aware diagnostics.
- **Gaps:** Eleven `cli_*.py` modules with cross-imports; no single
  documented place where a new command should live. Help text varies
  in tone. No `--json` output mode on the daily commands. No global
  `--quiet` / `--verbose` switch.
- **Risk:** Low for current users, **Medium** for commercial UX — a
  professional CLI needs machine-parsable output for scripting.
- **Recommendation:** Freeze the daily-command set, add a `--json` output
  contract for `ask`, `edit`, `apply`, `run`, `doctor`, `version`, `release
  preflight`. Document a CLI-author skill (`cli_*.py` boundaries, help-text
  style, exit codes).

### 2.2 Agent loop and action model

**Where:** `src/safecode/agent/loop.py` (567 LOC), `agent/orchestrator.py`,
`agent/schemas.py`, `agent/pending_action.py`, `agent/planner.py`,
`agent/session.py`, `agent/prompts.py`.

- **Strengths:** Typed pending actions (v2.8.3); typed agent-contract
  schemas with explicit `LLMContractViolation` and `RecoverableContractFailure`
  (v2.9.1); bounded retry; deterministic scripted client; tool-intent
  router; structured `AgentJournalStore` with versioned subagent payload
  (v2.9.6).
- **Gaps:** Loop file is 567 LOC and concentrates planning, tool routing,
  subagent enrichment, redaction, retry, and pending-action serialization.
  Real-LLM behavior is only exercised by mocks. Plan vocabulary is a flat
  list of strings; no DAG, no re-planning. Loop has no token-budget back-
  pressure; large context is just truncated to 12000 chars at the
  client edge.
- **Risk:** **Medium** — usable today, but unprepared for real,
  long-running tasks against a real provider.
- **Recommendation:** Split `loop.py` into `loop_step.py`,
  `loop_recovery.py`, `loop_context_enrichment.py`. Introduce an explicit
  token budget that flows from `ContextBudgetManager` to the LLM client.
  Add re-planning (`plan_v2` action). Promote the agent-contract schema
  to a stable v3.x experimental→supported transition only after
  multi-provider evidence.

### 2.3 Patch / pending / apply lifecycle

**Where:** `src/safecode/patch/parser.py`, `validator.py`, `applier.py`,
`diff.py`, `models.py`; `src/safecode/checkpoint/manager.py`,
`checkpoint/models.py`.

- **Strengths:** Public contract, snapshot-tested, hash-chained audit,
  rollback always available, `PatchProposal` round-trippable. This is the
  strongest area of the codebase.
- **Gaps:** Patch language is custom (`*** Begin Patch / *** Update File /
  SEARCH / REPLACE / *** End Patch`); no support for unified-diff input,
  no support for binary or rename ops, no support for partial-apply with
  conflicts. Validator does not yet integrate language-aware checks
  (e.g., Python AST syntax check for `.py` edits).
- **Risk:** Low — current shape is safe and works.
- **Recommendation:** Keep the schema frozen. Add an *experimental*
  unified-diff intake adapter behind a feature flag. Add an opt-in
  language-aware post-validation hook (`py_compile`, `tsc --noEmit`,
  `cargo check`) gated by detected stack.

### 2.4 Shell and sandbox safety boundaries

**Where:** `src/safecode/shell/`, `src/safecode/policy/commands.py`,
`policy/audit.py`, `src/safecode/sandbox/` (14 modules including
`adapter.py`, `planner.py`, `strategy.py`, `execution.py`, `approvals.py`,
`preflight.py`, `docker.py`, `seatbelt.py`, `bubblewrap.py`, `filesystem.py`,
`network.py`).

- **Strengths:** `block_high_risk`, argv exec (no shell string), atomic
  single-use approval, project-bound trust roots, network default off,
  82 cross-backend security evals (v2.4.3). Strategy split (v2.8.2) keeps
  recommendation pure.
- **Gaps:** Only the Noop adapter actually executes commands; Docker,
  Seatbelt, Bubblewrap remain *planners*, not executors. No process
  isolation verified for the Noop path beyond `subprocess.run(shell=False,
  env={})`. No syscall filter / namespace verification on Linux.
  Approval-store layout (one file per approval) does not document a
  rotation/GC policy.
- **Risk:** **High** for any backend beyond Noop — security evals exist
  but real execution paths are not wired.
- **Recommendation:** Before promoting any real backend, complete:
  Docker → Seatbelt → Bubblewrap execution paths behind explicit flags,
  each gated by its own preflight test suite. Document approval GC.
  Add a `sac sandbox doctor` that explains why a backend was/wasn't
  selected.

### 2.5 MCP integration

**Where:** `src/safecode/mcp/config.py`, `discovery.py`, `runner.py`
(562 LOC), `loop_executor.py`, `proposal.py`, `schema.py`.

- **Strengths:** Static schema-based classification (v2.9.4), call-arg
  validation (v2.9.5), proposal/approval gate for writes, redacted
  results. Schema-less workloads still fall back to keyword classifier.
- **Gaps:** No real JSON-RPC client. No process lifecycle management for
  MCP servers (start/stop/timeout/restart). No per-server permission
  scoping beyond a global read/write flag. No streaming/SSE handling.
- **Risk:** **High** — labeled experimental, but this is the gap most
  visible to users coming from other agents (Claude Code, Cursor, Cline)
  where MCP "just works."
- **Recommendation:** Treat MCP as a v3.3.x flagship surface. Add a
  small JSON-RPC stdio client with timeouts and audit. Keep the schema
  shim as the classification entry point; the runner becomes "shim
  + transport." Per-server permission scopes go into `.sac/mcp.toml`.

### 2.6 Subagent system

**Where:** `src/safecode/subagents/task.py`, `runner.py`, `executor.py`,
`payload.py` (v2.9.6), `journal_adapter.py`, `merge.py`, `merge_policy.py`.

- **Strengths:** File-backed tasks, journal-boundary redaction
  (v2.8.7), versioned payload with tolerant loading (v2.9.6), adversarial
  tests (folded v2.9.7). Read-only by design.
- **Gaps:** Single subagent at a time, synchronous dispatch, no
  cancellation, no parallel result synthesis. The "merge review" surface
  bounds findings but does not actually resolve conflicting observations.
  No notion of subagent-specific provider/model.
- **Risk:** **Medium-High** — current design will not scale to
  multi-task investigations.
- **Recommendation:** Defer concurrency until provider reliability
  (Section 2.10 / 3.1) lands. When it lands, add a bounded worker pool
  (max-2 by default) with deterministic merge order. Keep read-only as
  the default boundary.

### 2.7 Tool registry and ToolSpec contract

**Where:** `src/safecode/tools/registry.py`, `adapter.py`, `gate.py`.

- **Strengths:** Snapshot-tested, versioned (v2.9.8), invariants enforced.
- **Gaps:** Registry is a hard-coded module-level list. No discovery
  mechanism. No external-plugin ABI (intentional for v3.0).
- **Risk:** Low. Intentionally local.
- **Recommendation:** Keep local through v3.x. Plan a v4.x decision
  point on whether to expose a plugin ABI; do not promise it earlier.

### 2.8 Eval / replay / snapshot system

**Where:** `src/safecode/eval/runner.py`, `loop_runner.py`, `failures.py`,
`fixtures.py`, `loader.py`, `cases.py`.

- **Strengths:** Replayable trace, 11-value `FailureCategory` taxonomy,
  per-fixture snapshots in `tests/snapshots/loop/`, performance budgets
  attached to results (v2.5.4), CI gate (v2.9.3 advisory).
- **Gaps:** Fixture suite is six small scenarios. No realistic
  repo-scale fixtures (large monorepo, multi-language, generated code).
  No comparison to a held-out baseline (the snapshot *is* the
  baseline). No live-provider eval lane.
- **Risk:** Medium — current evals prevent regressions in the loop
  contract, but they do not measure "is this agent good at coding."
- **Recommendation:** Add a `golden-repos/` corpus (3-5 real repos
  cloned at fixed SHAs), each with a task list. Add a live-provider
  eval lane behind explicit credentials, advisory-only in CI.

### 2.9 Release / preflight / version governance

**Where:** `src/safecode/release/` (14 modules), `cli_ops.py` release
sub-app, `docs/install-update.md`, `tests/test_release_*`.

- **Strengths:** Preflight is the single gate (v2.6.11), versions-governance
  guard ties `versions.json` to the git tag (v2.7.8), changelog generator,
  docs-finalization guard, smoke tests, metadata audit.
- **Gaps:** No signed release. No PyPI publication automation. No
  `--pre` channel for experimental flags. No update-check on
  `sac doctor`.
- **Risk:** Medium for commercial — package signing and an update
  channel are table stakes.
- **Recommendation:** Add a `release publish` subcommand that builds
  the wheel, signs it (Sigstore), and uploads to PyPI; gate behind
  `SAFECODE_PUBLISH=1` and tag presence.

### 2.10 LLM provider layer

**Where:** `src/safecode/llm/base.py` (Protocol), `mock.py` (190 LOC),
`openai_client.py` (126 LOC), `factory.py` (15 LOC).

- **Strengths:** Clean Protocol; mock client is exhaustive; OpenAI
  client passes patches through SafeCode parsing/validation; network
  policy is enforced before any request.
- **Gaps (heaviest area):** No retry, no exponential backoff, no
  rate-limit handling, no token accounting, no cost tracking, no
  streaming, no provider fan-out (Anthropic, Bedrock, Vertex,
  local OpenAI-shaped Ollama/vLLM), no structured-output guarantee
  beyond a hand-parsed JSON contract, no thinking-mode support, no
  prompt-caching contract, no model fallback chain.
- **Risk:** **High** for commercial — this is the single biggest gap
  between "stable runtime" and "commercial coding agent."
- **Recommendation:** v3.2.x flagship surface. See Section 5/6.

### 2.11 Docs and user-facing workflow

**Where:** `README.md`, `docs/mvp-user-guide.md`, `docs/install-update.md`,
`docs/public-contracts.md`, `docs/security/`, `docs/version-notes/`,
`docs/tutorials/`.

- **Strengths:** Public-contracts page is current; install/update doc is
  detailed; demo workflow is documented end-to-end; security review doc
  exists.
- **Gaps:** No "What is SafeCode for?" landing narrative. No comparison
  page vs. Claude Code / Cursor / Cline. No troubleshooting matrix
  beyond runtime logs. No multi-provider config recipe. No commercial
  onboarding path.
- **Risk:** Medium-High for commercial discoverability.
- **Recommendation:** Add `docs/why-safecode.md`, `docs/compare.md`,
  `docs/troubleshooting.md`, `docs/providers.md` (when v3.2.x lands).

### 2.12 Test architecture

96 test files. Coverage emphasis: sandbox security evals (8 files),
agent loop (7 files), release (12 files), MCP (5 files), subagent (3
files), patch (3 files), contracts/snapshots (2 files + snapshot trees).

- **Strengths:** Wide deterministic regression. Snapshot tests for
  contracts. Adversarial subagent tests. Performance budgets recorded
  per replay run.
- **Gaps:** Almost no live-provider tests (intentional). Minimal
  property-based tests (no `hypothesis`). Test runtime not measured.
  No mutation-testing or coverage gate.
- **Risk:** Low for regressions, Medium for *novel* failures.
- **Recommendation:** Add `hypothesis`-based properties on patch
  parser, redactor, audit chain. Add `coverage.py` opt-in. Keep
  live-provider evals advisory.

---

## 3. Product Capability Gap Analysis

Comparison against what a "complete commercial local coding agent"
delivers. "Current" reflects v3.0.0; "Gap" is what needs to land.

### 3.1 Real LLM provider reliability and contract hardening
- **Current:** OpenAI-compatible synchronous client, no retry, no
  streaming, no fan-out.
- **Gap:** retry with jitter; rate-limit/Retry-After handling; streaming
  with cancellation; token + cost accounting per session; structured-output
  enforcement (JSON schema validation at the client edge before agent
  contract parsing); provider fan-out (Anthropic, Bedrock/Vertex, local
  OpenAI-shaped Ollama/vLLM); prompt-caching headers when supported; model
  fallback chain.

### 3.2 End-to-end coding workflow UX
- **Current:** `ask → edit → apply → rollback`, plus `run` for shell.
- **Gap:** "agent autopilot" loop (multi-step plan executed under
  approvals); inline diff edit-in-place; mid-step retry-from-failure;
  visual approval prompt richer than plain text; better progress
  indication during long tasks; idempotent "resume" command.

### 3.3 Multi-turn task memory and planning
- **Current:** Per-session `AgentJournalStore`; project-level
  `state/memory/` minimal store.
- **Gap:** Cross-session memory of "what we tried for this task";
  re-planning when validation fails; semantic dedup of past observations;
  user-editable memory store with redaction.

### 3.4 Repo intelligence and context ranking
- **Current:** `FileIndexer`, `PythonSymbolIndex`, `RepoMap`,
  `ContextSelector`.
- **Gap:** Symbol index for non-Python (TS, Go, Rust, Java); BM25 / TF-IDF
  ranking; optional embedding index (local-only, no network); call-graph
  for follow-the-symbol; "files touched recently in git" signal; cache
  with mtime invalidation.

### 3.5 Test / build / debug automation
- **Current:** `project_detector` detects pytest/uv/npm/cargo; `sac test
  run` exists; demo workflow exercises failing-test repair.
- **Gap:** Build-failure diagnosis loop (capture stderr → propose patch →
  reapply); auto-detect test command per language; flaky-test detection;
  per-language linter integration; `sac fix` shortcut.

### 3.6 MCP real server lifecycle and permissions
- **Current:** Static schema, classification, proposal gate.
- **Gap:** Stdio JSON-RPC client; server start/stop/timeout/restart;
  per-server scopes (`read_only`, `write_proposal`, `denied`); audit on
  every MCP call; `sac mcp doctor` per-server.

### 3.7 Subagent concurrency and result synthesis
- **Current:** Single, read-only, file-based.
- **Gap:** Bounded worker pool; deterministic merge ordering; subagent
  cancellation; LLM-driven synthesis (the *parent* agent reads merged
  findings instead of raw concatenation).

### 3.8 IDE / editor integration
- **Current:** `sac ide` writes a `pending.diff` and prints URIs.
- **Gap:** VS Code extension manifest backed by `SafeCodeLocalAPI`;
  diff preview in editor pane; approval prompt as a webview;
  status-bar session indicator.

### 3.9 TUI or richer local UI
- **Current:** `sac tui dashboard` is a static Rich panel.
- **Gap:** Interactive TUI (Textual): session list, plan view, pending
  diff preview, approval prompt, journal tail. Optional, not required for
  v3.x but a major UX upgrade.

### 3.10 Install / update / diagnostics
- **Current:** `pip install -e .[dev]`, `uv tool install .`, `sac
  doctor`, Docker image.
- **Gap:** Signed wheel on PyPI; `sac doctor` checks current version vs.
  latest known tag; `pipx`/`brew` documented; offline-install recipe.

### 3.11 Project onboarding and config wizard
- **Current:** `sac setup`, `sac quickstart`.
- **Gap:** Stack-aware presets (auto-pick test/build commands), provider
  + model wizard, hook templates per language, demo materialization tied
  to detected language.

### 3.12 Policy management for different trust levels
- **Current:** Three presets, two aliases, project cannot lower user
  policy.
- **Gap:** Per-directory or per-repo trust roots; "ephemeral trust"
  (one session); explicit policy diff command (`sac config diff
  --against strict`); audited policy-changes log.

### 3.13 Observability, reports, debugging
- **Current:** Runtime logs JSONL, audit JSONL with hash chain, eval
  dashboard renderer.
- **Gap:** `sac trace export --since ...`; OpenTelemetry exporter
  (optional); per-session HTML report; structured error taxonomy in
  `sac doctor` output.

### 3.14 Performance and scalability
- **Current:** `PerformanceBudget` per replay; no live-session metric.
- **Gap:** Live-session metrics emitted to `.sac/metrics.jsonl`;
  context-pack size budgeting; index incremental update for large repos;
  benchmark suite (`sac eval bench`).

### 3.15 Security hardening and threat model
- **Current:** v2.6 security review doc, sandbox security evals, redactor,
  approval atomicity, network default off.
- **Gap:** Documented threat model per persona (curious user, malicious
  config, malicious MCP server, malicious model output); STRIDE for
  each boundary; periodic security review cadence (semi-annual).

### 3.16 Documentation and examples
- **Current:** mvp-user-guide, install-update, public-contracts, demo
  workflow, version notes, security review.
- **Gap:** "Why SafeCode" landing page; provider configuration matrix;
  one tutorial per stack (Python, TypeScript, Go); troubleshooting matrix.

### 3.17 CI / release maturity
- **Current:** GH Actions on Python 3.11, full pytest, loop eval
  advisory, release preflight local-only.
- **Gap:** Multi-Python matrix (3.11, 3.12, 3.13); macOS + Linux + Windows
  runners; sigstore signing; PyPI publish on tag; nightly job that
  runs loop eval + live-provider eval (when keys present).

---

## 4. Commercial Readiness Table

Priority key: P0 = blocker for first commercial release; P1 = required
for "1.0 commercial"; P2 = quality-of-life polish; P3 = future / optional.
Risk: H/M/L of shipping as-is.

| Area | Current Status | Missing For Commercial | Priority | Risk | Suggested Version | Notes |
|---|---|---|---|---|---|---|
| Real LLM reliability | Synchronous OpenAI-compat only | Retry, streaming, token/cost accounting, multi-provider, structured-output validation | **P0** | H | v3.2.x | Single biggest gap |
| End-to-end coding UX | `edit/apply/rollback` works | Autopilot loop, inline retry-from-failure, resume | **P0** | M | v3.1.x | Build on stable patch substrate |
| Multi-turn memory + replan | Per-session journal | Cross-session memory, replan on validation fail | **P1** | M | v3.1.x → v3.2.x | Needs provider reliability first |
| Repo intelligence | File + Python symbols + RepoMap | Multi-language symbols, BM25/embeddings, recency signal | **P1** | M | v3.1.x → v3.4.x | Embeddings stay local-only |
| Test/build/debug auto | Detector + `sac test run` | Build-failure diagnosis loop, `sac fix` | **P1** | M | v3.1.x | Hooks into autopilot |
| MCP real lifecycle | Static schema + classification | JSON-RPC stdio client, per-server scopes, lifecycle | **P0** | H | v3.3.x | Visible parity gap with peers |
| Subagent concurrency | Single, read-only, file-based | Bounded pool, LLM synthesis, cancellation | **P1** | M-H | v3.4.x | Defer until v3.2.x stable |
| IDE integration | Manifest + diff file URIs | VS Code extension + LocalAPI | **P1** | M | v3.5.x | After UX is stable |
| TUI surface | Static dashboard | Interactive Textual TUI | **P2** | L | v3.5.x | Nice-to-have |
| Install/update | pip + uv tool + Docker | PyPI signed wheel, update check, pipx/brew | **P1** | M | v3.6.x | Table stakes |
| Onboarding wizard | `setup` + `quickstart` | Stack-aware presets, provider wizard, language demos | **P1** | L | v3.1.x | Compounding UX win |
| Policy management | Three presets + lowering rules | Per-dir trust, ephemeral trust, policy diff | **P2** | L | v3.6.x | After commercial v1 |
| Observability | Runtime + audit JSONL | Per-session HTML report, OTel exporter, error taxonomy in doctor | **P2** | L | v3.6.x | OTel opt-in |
| Performance | Replay-time budgets | Live metrics, incremental index, bench suite | **P2** | M | v3.4.x → v3.6.x | Tied to repo intel |
| Security hardening | Sandbox evals + redactor + atomicity | Documented threat model per persona, semi-annual review cadence | **P1** | M | v3.6.x | Audit deliverable |
| Documentation | Guides + contracts + security review | "Why SafeCode", provider matrix, stack tutorials, troubleshooting | **P1** | L | v3.1.x → v3.6.x | Continuous |
| CI / release maturity | One Python, advisory eval, local preflight | Multi-Python matrix, multi-OS, sigstore, PyPI publish, nightly evals | **P0** | M | v3.6.x | Required before public sell |

---

## 5. Proposed Roadmap

Each range below has a Theme, a "Why now," likely entry points/files,
acceptance criteria, regression tests, and the user-visible outcome.
Ranges are sized to a single-maintainer cadence consistent with the
v2.8-v3.0 train: 5-10 patch tags per range, one per landed batch.

### v3.1.x — Product UX and workflow completion

- **Theme:** Make the daily coding loop feel like a real product without
  changing safety semantics.
- **Why now:** v3.0 froze the safety substrate; UX is the next-highest
  leverage area and does not require provider work.
- **Entry points:** `src/safecode/agent/orchestrator.py`,
  `agent/loop.py`, `cli_agent.py`, `cli_quickstart.py`, `cli_core.py`,
  `setup.py`, `demo/`, `context/selector.py`, `index/repo_map.py`,
  `project/`, `cli_test_demo.py`.
- **Acceptance:**
  - `sac agent run "goal"` executes a multi-step plan under approvals,
    with a documented stop-and-resume contract.
  - `sac edit` supports `--retry-from-last-failure`.
  - `sac fix` exists: run last failing test, propose patch, await
    approval.
  - All daily commands gain a `--json` output mode with a documented
    schema.
  - `sac quickstart` becomes stack-aware (detects Python/TS/Go/Rust and
    suggests the right demo workflow).
- **Regression tests:** Extend `test_agent_loop_*`, `test_quickstart`,
  `test_cli_output_honesty`, add `tests/test_cli_json_output.py`,
  `tests/test_agent_autopilot_resume.py`.
- **User-visible outcome:** A new user runs `sac quickstart` and gets a
  loop that "just works" end to end on the demo, with honest progress
  and a one-command resume.

### v3.2.x — Real LLM provider reliability

- **Theme:** Promote real-provider behavior from experimental to
  supported-with-evidence.
- **Why now:** v3.1.x's autopilot needs a reliable client; nothing
  else compounds without it.
- **Entry points:** `src/safecode/llm/base.py`, `llm/openai_client.py`,
  `llm/factory.py`, new `llm/anthropic_client.py`, new `llm/retry.py`,
  new `llm/cost.py`, new `llm/stream.py`, new `llm/providers.md` doc.
- **Acceptance:**
  - Provider Protocol grows `stream()` and `ask_with_tools()`.
  - Retry with jitter + Retry-After honoring; max 3 by default;
    per-attempt event in audit/runtime log.
  - Token + cost accounting per session; `sac doctor` reports last-
    session cost; data lives in `.sac/sessions/<id>/cost.json`.
  - Anthropic provider lands behind `SAFECODE_LLM_PROVIDER=anthropic`
    with prompt caching support.
  - Live-provider eval lane lands in CI behind `LIVE_LLM_KEYS` secret,
    advisory.
  - Public-contract docs add an "LLM provider contract" section,
    promoted from experimental to supported.
- **Regression tests:** New `tests/test_llm_retry.py`,
  `tests/test_llm_cost_accounting.py`,
  `tests/test_llm_streaming.py`,
  `tests/test_llm_anthropic_client.py` (mocked transport),
  `tests/test_provider_contract_snapshot.py`.
- **User-visible outcome:** Real-provider sessions reliably complete on
  flaky networks; users see token + cost reporting; Anthropic users
  get prompt caching.

### v3.3.x — MCP and external tool execution hardening

- **Theme:** Real MCP execution under safety gates.
- **Why now:** With reliable providers, MCP becomes the next visible
  capability gap.
- **Entry points:** `src/safecode/mcp/runner.py`, `mcp/loop_executor.py`,
  `mcp/proposal.py`, `mcp/discovery.py`, new `mcp/transport_stdio.py`,
  new `mcp/lifecycle.py`, `cli_mcp.py`, `policy/commands.py` for
  per-server scopes.
- **Acceptance:**
  - Stdio JSON-RPC client lands with timeouts, audit on every call,
    server-process lifecycle (`start`, `stop`, `restart`, `timeout`).
  - Per-server permission scopes documented in `.sac/mcp.toml`:
    `denied`, `read_only`, `write_proposal_required`.
  - Approval-gated MCP write proposals execute end-to-end against a
    mock JSON-RPC server in tests.
  - `sac mcp doctor <server>` reports binary path, version, and last
    call status.
  - Public-contract docs promote MCP read execution to supported once
    one full evaluation cycle passes.
- **Regression tests:** New `tests/test_mcp_transport_stdio.py`,
  `tests/test_mcp_lifecycle.py`, `tests/test_mcp_per_server_scopes.py`,
  `tests/test_mcp_write_proposal_end_to_end.py`.
- **User-visible outcome:** Users can register real MCP servers and
  call them within SafeCode's approval/audit boundary.

### v3.4.x — Subagent orchestration and synthesis

- **Theme:** Bounded concurrent subagents with LLM-driven synthesis.
- **Why now:** Subagents are most useful for repo investigation, which
  needs MCP + real LLM behind it.
- **Entry points:** `src/safecode/subagents/runner.py`,
  `subagents/executor.py`, `subagents/merge.py`, `subagents/merge_policy.py`,
  `agent/loop.py` for parent-side enrichment, new `subagents/pool.py`,
  new `subagents/synthesis.py`.
- **Acceptance:**
  - Default max-2 parallel read-only subagents; configurable via
    `SAFECODE_SUBAGENT_MAX`.
  - Deterministic merge order (by `task_id`).
  - Cancellation: parent can revoke a running subagent within 5s.
  - LLM synthesis: parent calls a `synthesize_findings` prompt with the
    merged list before consuming.
  - Public-contract docs promote subagent v2 payload to supported.
- **Regression tests:** New `tests/test_subagent_pool.py`,
  `tests/test_subagent_cancellation.py`,
  `tests/test_subagent_synthesis.py`. Extend
  `test_subagent_journal_payload_versioning` for v2 payload.
- **User-visible outcome:** "Investigate this codebase" tasks complete
  faster with bounded concurrency and a coherent synthesized summary.

### v3.5.x — IDE/TUI product surface

- **Theme:** First-class editor + interactive TUI.
- **Why now:** Loop + provider + MCP + subagents are reliable; UX
  scales with surface area.
- **Entry points:** `src/safecode/ide/bridge.py`, `ide/manifest.py`,
  new `vscode-extension/` repo (separate dist), new `src/safecode/tui/`
  interactive layer (Textual).
- **Acceptance:**
  - VS Code extension publishes; uses `SafeCodeLocalAPI` over a
    documented stdio JSON-RPC contract (re-using the MCP transport).
  - Diff preview, approval prompt, journal tail all in the editor.
  - `sac tui` becomes interactive (Textual): session list, plan view,
    pending diff, approval prompt, journal tail.
  - Public-contract docs add "Editor bridge contract" as experimental,
    not yet supported.
- **Regression tests:** New `tests/test_ide_bridge_jsonrpc.py`,
  `tests/test_tui_interactive_smoke.py` (snapshot of Textual renderable).
- **User-visible outcome:** SafeCode is usable from within VS Code with
  the same safety semantics; terminal users get a real TUI.

### v3.6.x — Commercial hardening, packaging, performance, docs

- **Theme:** Make it shippable, supportable, and sellable.
- **Why now:** Function landed; now correctness, distribution, and
  documentation become the long pole.
- **Entry points:** `pyproject.toml`, `.github/workflows/`,
  `src/safecode/release/publish.py` (new), `src/safecode/doctor.py`,
  `docs/why-safecode.md` (new), `docs/compare.md` (new),
  `docs/providers.md` (new), `docs/troubleshooting.md` (new),
  `docs/security/threat-model-v3.6.md` (new).
- **Acceptance:**
  - Sigstore-signed wheel on PyPI; `pipx install safecode-agent` works;
    Homebrew formula or tap published.
  - CI matrix: Python 3.11/3.12/3.13 × {linux, macos}; Windows on a
    smoke job.
  - `sac doctor` reports installed version vs. latest tag (over HTTPS,
    no telemetry).
  - OTel exporter behind `SAFECODE_OTEL_EXPORTER=...`.
  - Per-session HTML report (`sac report html`).
  - Threat model document and semi-annual security-review cadence
    captured in `docs/security/`.
  - "Why SafeCode" landing, provider matrix, three stack tutorials,
    troubleshooting matrix all merged.
- **Regression tests:** New `tests/test_release_publish_dry_run.py`,
  `tests/test_doctor_update_check.py`, `tests/test_report_html.py`,
  `tests/test_otel_exporter.py`.
- **User-visible outcome:** A new user can `pipx install` SafeCode,
  follow a one-page tutorial, and use it for a real task with a real
  provider, all on a signed, multi-platform build.

---

## 6. Concrete Subtask Plan

Each task is sized for a single Claude Code / Sonnet session. Dependencies
reference task IDs. Risk: H/M/L of regression in landing.

### v3.1.x tasks (UX and workflow completion)

| Version | Task ID | Task Name | Goal | Main Files | Tests | Acceptance | Deps | Risk |
|---|---|---|---|---|---|---|---|---|
| v3.1.0 | T-3.1.0-A | json-output-foundation | Add a shared `--json` flag + serializer to every daily command | `cli_core.py`, new `cli_shared_json.py`, `cli_agent.py`, `cli_ops.py` | new `tests/test_cli_json_output.py` | `sac ask/edit/apply/run/doctor/version --json` returns documented schema; non-json unchanged | — | M |
| v3.1.0 | T-3.1.0-B | autopilot-agent-run | Add `sac agent run "goal"` executing multi-step plan under approvals | `cli_agent.py`, `agent/orchestrator.py`, `agent/loop.py` | new `tests/test_agent_autopilot.py` | Loop drives plan to completion or stop-for-user; journal records each step | T-3.1.0-A | H |
| v3.1.1 | T-3.1.1-A | resume-session | Add `sac agent resume <session_id>`; loop picks up last pending action | `agent/session.py`, `cli_agent.py`, `agent/loop.py` | new `tests/test_agent_resume.py` | Resume after `stop_for_user` continues from same step deterministically | T-3.1.0-B | M |
| v3.1.1 | T-3.1.1-B | edit-retry-from-failure | `sac edit --retry-from-last-failure` reuses last failure context | `cli_agent.py`, `agent/orchestrator.py`, `state/journal.py` | new `tests/test_edit_retry.py` | After a failed apply, next edit ingests last validator/test error | T-3.1.0-B | M |
| v3.1.2 | T-3.1.2-A | sac-fix-command | Add `sac fix` shortcut: run last failing test → propose patch → await approval | new `cli_fix.py`, `project/`, `agent/orchestrator.py` | new `tests/test_sac_fix.py` | `sac fix` works on demo failing-test-repair without manual chaining | T-3.1.1-B | M |
| v3.1.3 | T-3.1.3-A | stack-aware-quickstart | Detect stack and recommend per-language demo + commands | `cli_quickstart.py`, `project/`, `demo/` | extend `tests/test_quickstart.py` | Quickstart recognizes pyproject/package.json/go.mod/Cargo.toml and adapts | — | L |
| v3.1.3 | T-3.1.3-B | onboarding-provider-wizard | `sac setup --wizard` walks through provider/model and writes config | `cli_quickstart.py`, `setup.py`, `config.py` | new `tests/test_setup_wizard.py` | Wizard never enables network without explicit user confirmation | T-3.1.3-A | M |
| v3.1.4 | T-3.1.4-A | progress-indicator | Add a Rich progress + status line to long-running commands | `cli_core.py`, `agent/orchestrator.py` | new `tests/test_cli_progress.py` (snapshot Rich) | Non-TTY mode is silent; TTY mode shows step counter | — | L |
| v3.1.5 | T-3.1.5-A | repo-recency-signal | `ContextSelector` weights recently-git-touched files higher | `context/selector.py`, `index/repo_map.py` | extend `tests/test_repo_map.py`, new `tests/test_context_recency.py` | Recency raises rank without breaking existing snapshots | — | M |
| v3.1.6 | T-3.1.6-A | release-3.1.0-batch-docs | Update README + `docs/mvp-user-guide.md` for autopilot, fix, resume | `README.md`, `docs/mvp-user-guide.md`, `docs/version-notes/v3.1.6-*.md` | `tests/test_mvp_docs.py`, `tests/test_release_docs_guard.py` | Docs guard passes; preflight passes | T-3.1.0 through T-3.1.5 | L |

### v3.2.x tasks (LLM provider reliability)

| Version | Task ID | Task Name | Goal | Main Files | Tests | Acceptance | Deps | Risk |
|---|---|---|---|---|---|---|---|---|
| v3.2.0 | T-3.2.0-A | llm-retry-jitter | Add `safecode/llm/retry.py` with bounded retry + jitter + Retry-After | `llm/retry.py`, `llm/openai_client.py` | new `tests/test_llm_retry.py` | Mocked transport simulating 429/503 succeeds on retry; max attempts respected | — | M |
| v3.2.0 | T-3.2.0-B | llm-cost-accounting | Add `safecode/llm/cost.py`; record usage in `.sac/sessions/<id>/cost.json` | `llm/cost.py`, `llm/openai_client.py`, `agent/session.py` | new `tests/test_llm_cost_accounting.py` | Session ends with totals; `sac doctor` shows last session cost | — | M |
| v3.2.1 | T-3.2.1-A | llm-streaming | Provider Protocol gains `stream()`; orchestrator consumes chunks | `llm/base.py`, `llm/openai_client.py`, `llm/stream.py`, `agent/orchestrator.py` | new `tests/test_llm_streaming.py` | Streamed final output equals non-streamed equivalent | T-3.2.0-A | M-H |
| v3.2.2 | T-3.2.2-A | structured-output-validation | Validate JSON-schema before parsing into agent contract | `llm/openai_client.py`, `agent/schemas.py` | new `tests/test_llm_structured_output.py` | Malformed JSON triggers `RecoverableContractFailure`, not crash | — | M |
| v3.2.3 | T-3.2.3-A | anthropic-provider | Add `llm/anthropic_client.py` behind factory key `anthropic` | `llm/anthropic_client.py`, `llm/factory.py`, `config.py` | new `tests/test_llm_anthropic_client.py` (mocked) | All agent-contract methods round-trip on mocked Anthropic transport | T-3.2.1-A, T-3.2.2-A | M |
| v3.2.4 | T-3.2.4-A | provider-fan-out-config | Provider chain `primary → fallback`; switch on hard error | `config.py`, `llm/factory.py`, `agent/orchestrator.py` | new `tests/test_llm_provider_fanout.py` | Primary failure routes to fallback; both must pass network policy | T-3.2.3-A | M |
| v3.2.5 | T-3.2.5-A | live-provider-ci-lane | Add CI job gated by `LIVE_LLM_KEYS`; advisory | `.github/workflows/ci.yml`, `tests/live/` | new `tests/test_ci_live_lane.py` | Lane runs only when secret present; otherwise skipped | T-3.2.4-A | L |
| v3.2.6 | T-3.2.6-A | docs-providers-and-promote | Add `docs/providers.md`; promote provider contract to supported | `docs/providers.md`, `docs/public-contracts.md`, snapshot tests | extend `tests/test_public_contract_snapshots.py` | New snapshot for provider contract; docs guard passes | All v3.2 | L |

### v3.3.x tasks (MCP hardening)

| Version | Task ID | Task Name | Goal | Main Files | Tests | Acceptance | Deps | Risk |
|---|---|---|---|---|---|---|---|---|
| v3.3.0 | T-3.3.0-A | mcp-stdio-transport | Implement stdio JSON-RPC client with timeouts | `mcp/transport_stdio.py`, `mcp/runner.py` | new `tests/test_mcp_transport_stdio.py` | Round-trip request/response against a stub server | — | M |
| v3.3.1 | T-3.3.1-A | mcp-lifecycle | Server start/stop/restart/timeout; PID + audit | `mcp/lifecycle.py`, `cli_mcp.py` | new `tests/test_mcp_lifecycle.py` | `sac mcp start/stop/restart` audited; never orphans processes | T-3.3.0-A | M-H |
| v3.3.2 | T-3.3.2-A | mcp-per-server-scopes | `.sac/mcp.toml` scopes per server; runner enforces | `mcp/config.py`, `mcp/runner.py`, `mcp/proposal.py` | new `tests/test_mcp_per_server_scopes.py` | `denied` blocks; `read_only` requires no approval; `write_proposal_required` gates | T-3.3.1-A | M |
| v3.3.3 | T-3.3.3-A | mcp-write-proposal-e2e | Wire approval-gated MCP writes against a mock server | `mcp/proposal.py`, `mcp/runner.py`, `mcp/loop_executor.py` | new `tests/test_mcp_write_proposal_end_to_end.py` | Proposal → approval → execution; result_record stored | T-3.3.2-A | M-H |
| v3.3.4 | T-3.3.4-A | mcp-doctor | `sac mcp doctor [server]` reports status | `cli_mcp.py`, `doctor.py` | new `tests/test_mcp_doctor.py` | Returns binary path, last call status, classification source | — | L |
| v3.3.5 | T-3.3.5-A | mcp-promote-contract | Promote MCP read execution to supported in contracts | `docs/public-contracts.md`, snapshot tests | extend `tests/test_public_contract_snapshots.py` | New contract snapshot for MCP transport + scope vocabulary | All v3.3 | L |

### v3.4.x tasks (subagent orchestration)

| Version | Task ID | Task Name | Goal | Main Files | Tests | Acceptance | Deps | Risk |
|---|---|---|---|---|---|---|---|---|
| v3.4.0 | T-3.4.0-A | subagent-pool | Bounded worker pool, max-2 default | `subagents/pool.py`, `subagents/runner.py` | new `tests/test_subagent_pool.py` | Deterministic ordering; cap enforced; existing tests pass | — | M |
| v3.4.1 | T-3.4.1-A | subagent-cancellation | Parent revokes within 5s; idempotent | `subagents/executor.py`, `agent/loop.py` | new `tests/test_subagent_cancellation.py` | Cancelled task records `blocked=True`, no orphan files | T-3.4.0-A | M |
| v3.4.2 | T-3.4.2-A | subagent-synthesis | Parent calls `synthesize_findings` before consuming merged list | `subagents/synthesis.py`, `agent/loop.py` | new `tests/test_subagent_synthesis.py` | Synthesis output redacted; merged list unchanged | T-3.4.0-A | M |
| v3.4.3 | T-3.4.3-A | subagent-payload-v2 | Bump `SubagentDispatchPayload.payload_version=2` with synthesis fields | `subagents/payload.py`, `subagents/journal_adapter.py` | extend `tests/test_subagent_journal_payload_versioning.py` | v1 still loads tolerantly; v2 round-trips | T-3.4.2-A | M |

### v3.5.x tasks (IDE/TUI surface)

| Version | Task ID | Task Name | Goal | Main Files | Tests | Acceptance | Deps | Risk |
|---|---|---|---|---|---|---|---|---|
| v3.5.0 | T-3.5.0-A | localapi-jsonrpc | Expose `SafeCodeLocalAPI` over stdio JSON-RPC (reuse MCP transport) | new `api/jsonrpc.py`, `api.py` | new `tests/test_ide_bridge_jsonrpc.py` | Round-trip ask/edit/apply via JSON-RPC; auditable | T-3.3.0-A | M-H |
| v3.5.1 | T-3.5.1-A | vscode-extension-skeleton | Publish skeleton extension to a separate repo with manifest | external repo + `ide/manifest.py` | manual smoke + `tests/test_ide_bridge.py` extended | Extension launches `sac api jsonrpc` and shows pending diff | T-3.5.0-A | M |
| v3.5.2 | T-3.5.2-A | tui-interactive | Textual TUI: session list, plan, pending diff, approval, journal | new `tui/app.py`, `tui/dashboard.py` | new `tests/test_tui_interactive_smoke.py` | Snapshot of widget tree matches; non-TTY exits gracefully | T-3.1.0-B | M |

### v3.6.x tasks (commercial hardening)

| Version | Task ID | Task Name | Goal | Main Files | Tests | Acceptance | Deps | Risk |
|---|---|---|---|---|---|---|---|---|
| v3.6.0 | T-3.6.0-A | release-publish | `sac release publish --dry-run/--sign` builds, signs (sigstore), uploads | `release/publish.py`, `cli_ops.py` | new `tests/test_release_publish_dry_run.py` | Dry-run reports steps; real publish requires tag + `SAFECODE_PUBLISH=1` | — | M |
| v3.6.0 | T-3.6.0-B | ci-matrix | CI matrix Python 3.11/3.12/3.13 × {linux, macos}; Windows smoke | `.github/workflows/ci.yml` | extend `tests/test_ci_workflow.py` | All combos green; loop eval still advisory | — | M |
| v3.6.1 | T-3.6.1-A | doctor-update-check | Doctor reports latest known tag (HTTPS, no telemetry) | `doctor.py` | new `tests/test_doctor_update_check.py` | Offline mode skips check; warning when stale | — | L |
| v3.6.2 | T-3.6.2-A | otel-exporter | Optional OTel exporter for runtime events + agent steps | new `trace/otel.py` | new `tests/test_otel_exporter.py` | Disabled by default; explicit env enables | — | M |
| v3.6.3 | T-3.6.3-A | report-html | `sac report html --session <id>` renders per-session HTML | `report/dashboard.py`, `cli_ops.py` | new `tests/test_report_html.py` | Self-contained HTML; deterministic for fixed input | — | L |
| v3.6.4 | T-3.6.4-A | threat-model-doc | Document threat model per persona + semi-annual review cadence | `docs/security/threat-model-v3.6.md` | `tests/test_security_review_docs.py` extended | Sections enforced; CI guards required headings | — | L |
| v3.6.5 | T-3.6.5-A | landing-docs | `docs/why-safecode.md`, `docs/compare.md`, `docs/troubleshooting.md` | docs | `tests/test_mvp_docs.py` extended | All linked from README; docs guard passes | — | L |
| v3.6.6 | T-3.6.6-A | commercial-v1-cut | Tag v3.6.6 as "commercial v1" milestone; update versions.json/SKILL.md | `pyproject.toml`, `versions.json`, SKILL | full preflight + smoke | preflight passes; tag and metadata aligned | all of v3.x | L |

---

## 7. Architecture Optimization Recommendations

### What should be refactored

1. **Split `agent/loop.py` (567 LOC).** Suggested boundary:
   - `loop_step.py` — single-step decide-and-execute.
   - `loop_recovery.py` — `RecoverableContractFailure` handling and retry.
   - `loop_context_enrichment.py` — subagent finding merge + redaction.
   - `loop_serialize.py` — pending-action persistence.
   Keep `AgentLoop` as the thin façade.
2. **Lift LLM client cross-cutting concerns into shared helpers.**
   `retry.py`, `cost.py`, `stream.py` should not be re-implemented per
   provider.
3. **CLI command-module conventions.** Document where new commands go
   (`cli_<area>.py`) and a one-page CLI-style guide for help text,
   exit codes, `--json` output, error messages.
4. **Sandbox planner vs. executor split per backend.** Each backend
   should have a `*_plan.py` and a `*_executor.py` so promotion from
   "dry run" to "real execution" is a single, reviewable diff.

### What should remain stable

- The eight v3.0 public contracts in `docs/public-contracts.md`.
- The `PatchProposal`/`PatchBlock` schema and patch grammar.
- `AuditEvent` field set and hash-chain semantics.
- `ToolSpec` field set and `REGISTRY_SCHEMA_VERSION="1"`.
- `SandboxExecutionProposal/Approval/ResultRecord` field sets.
- Daily CLI surface: `setup`, `quickstart`, `ask`, `edit`, `apply`,
  `rollback`, `run`, `doctor`, `version`, `release preflight/bump/changelog`.

### What should stay experimental (do not freeze yet)

- `SafeCodeLocalAPI` write methods (until v3.5.x JSON-RPC bridge is
  stable).
- LLM provider Protocol additions (`stream`, `ask_with_tools`) — promote
  only after v3.2.6.
- MCP transport (promote only after v3.3.5).
- Subagent v2 payload (promote only after v3.4.3).
- TUI/IDE surfaces (promote only after v3.5.x has run for a release
  train).
- `report html` and OTel exporter (always opt-in).

### What should become public contract later

- LLM provider contract → at v3.2.6 (`docs/providers.md` + snapshot).
- MCP read execution → at v3.3.5.
- Subagent v2 payload → at v3.4.3.
- IDE JSON-RPC surface → at v3.5.x mid-train.

### What should NOT be built yet (deferred / out of scope)

- Cloud / team / SaaS backend.
- Centralized policy server.
- External plugin ABI for `ToolSpec`.
- Telemetry / analytics service.
- Multi-user workspaces.
- Signed audit anchors with external CA.
- "Auto-fix on save" non-interactive mode without an explicit feature flag.

Reason: each of these would substantially expand the threat model and
violate the local-first, safety-first product direction. They are post-
v3.x decisions.

---

## 8. Definition Of Done For Commercial Product

Concrete criteria for "commercial v1 has basically landed" (target:
v3.6.6).

### Functional
- Autopilot loop (`sac agent run`) drives a multi-step task to
  completion or stop-for-user, deterministically resumable.
- `sac fix` and `sac edit --retry-from-last-failure` work on real
  repos in three stacks (Python, TypeScript, Go).
- MCP read calls execute against a real stdio JSON-RPC server through
  SafeCode's audit boundary; write proposals gate at approval.
- Two production LLM providers (OpenAI-compatible, Anthropic) supported
  with retry, streaming, cost accounting.
- Subagent pool supports bounded concurrency with synthesis.

### UX
- All daily commands offer a documented `--json` output.
- Onboarding wizard recommends provider/model/stack without enabling
  network unless the user confirms.
- Interactive TUI and VS Code extension cover the daily loop.
- Error messages include actionable next steps (`sac doctor`,
  `docs/troubleshooting.md`).

### Safety / security
- Threat model document covers four personas (curious user, malicious
  config, malicious MCP server, malicious model output) and lives in
  `docs/security/`.
- Semi-annual security review cadence documented and ack'd in
  `docs/security/`.
- Sandbox executes only on Docker/Seatbelt/Bubblewrap after each backend
  passes its own evals; Noop remains the default and is explicitly
  labeled.
- Approval atomicity and project-binding remain invariant; no change to
  the v3.0 sandbox lifecycle contract without a major version bump.

### Reliability
- LLM retry covers transient 429/503/network failures; mocked tests
  cover at least 8 failure modes.
- Live-provider CI lane has run cleanly for at least one full release
  train.
- Loop eval CI gate promoted from advisory to blocking.
- All public-contract snapshots match across the matrix.

### Performance
- Live-session metrics emitted to `.sac/metrics.jsonl`.
- Context-pack p50 size budget documented per language preset.
- Bench suite (`sac eval bench`) baseline captured at v3.6.0 and tracked.

### Documentation
- `docs/why-safecode.md`, `docs/compare.md`, `docs/providers.md`,
  `docs/troubleshooting.md`, three per-stack tutorials all merged and
  linked from README.
- Public contracts page reflects every promoted surface (provider, MCP,
  subagent v2) with explicit experimental labels for the rest.
- One end-to-end "first hour" tutorial per stack.

### Release / support
- Sigstore-signed wheels published to PyPI.
- `pipx install safecode-agent` works on macOS, Linux, and Windows
  (smoke).
- `sac doctor` warns when a newer tag is available (opt-out via env).
- Versioning policy documented: minor bumps may add experimental
  surfaces; patch bumps never change a public contract; major bumps
  reserved for contract changes.
- Release cadence: one minor every 4-6 weeks; one patch as needed; one
  security review per train.

---

## 9. Immediate Next Batch Prompts

Three ready-to-use prompts for Claude Code / Sonnet. Each prompt is
self-contained, scoped, and includes validation commands. Use them in
order.

### Prompt A — v3.1.0 first implementation batch

```text
You are implementing SafeCode Agent v3.1.0 (autopilot + JSON output)
from baseline v3.0.0.

Read first:
- .claude/skills/current/SKILL.md
- .claude/skills/shared/core-runtime.md
- docs/product-commercialization-roadmap.md  (Section 5 v3.1.x, Section 6 tasks T-3.1.0-A and T-3.1.0-B)
- docs/public-contracts.md
- src/safecode/cli.py, src/safecode/cli_agent.py, src/safecode/cli_core.py
- src/safecode/agent/orchestrator.py, src/safecode/agent/loop.py, src/safecode/agent/pending_action.py

Tasks (land in one commit per task ID):

T-3.1.0-A json-output-foundation
- Add a shared `--json` flag and JSON serializer used by `sac ask`, `sac edit`, `sac apply`, `sac run`, `sac doctor`, `sac version`, and `sac release preflight`.
- Create `src/safecode/cli_shared_json.py` with a typed `CLIJSONResponse` model and `render(...)`.
- Non-json output must remain byte-identical (snapshot existing CLI output where needed).
- Tests: new `tests/test_cli_json_output.py` covering all listed commands.

T-3.1.0-B autopilot-agent-run
- Add `sac agent run "goal"` that drives the existing AgentLoop to completion or stop-for-user.
- Reuse `AgentLoop.step()`, `pending_action_from_dict`, and journal events. Do NOT bypass approvals.
- New session if none active; resume current session if one exists and matches the goal.
- Tests: new `tests/test_agent_autopilot.py` using the scripted client and existing fixtures.

Hard constraints:
- Do not rename existing CLI commands or reorder arguments.
- Do not weaken diff/checkpoint/audit/rollback/policy/sandbox gates.
- Default LLM provider remains mock.
- All v3.0 public contract snapshots must keep passing.

After the batch:
- run targeted tests: `PYTHONPATH=src python3 -m pytest tests/test_cli_json_output.py tests/test_agent_autopilot.py -q`
- run full regression: `PYTHONPATH=src python3 -m pytest -q`
- run `PYTHONPATH=src python3 -m safecode.cli release preflight`
- bump pyproject.toml and src/safecode/__init__.py to 3.1.0
- add docs/version-notes/v3.1.0-autopilot-json-output.md
- update docs/version_implementation_matrix.md
- update .claude/skills/current/SKILL.md baseline
- run sac release sync-versions-json
- commit with message "Implement v3.1.0 autopilot-json-output" and tag v3.1.0
```

### Prompt B — v3.1.1 follow-up batch

```text
You are implementing SafeCode Agent v3.1.1 (resume + retry-from-failure)
on top of v3.1.0.

Read first:
- .claude/skills/current/SKILL.md
- docs/product-commercialization-roadmap.md  (Section 6 tasks T-3.1.1-A and T-3.1.1-B)
- src/safecode/agent/session.py, src/safecode/agent/loop.py, src/safecode/state/journal.py
- src/safecode/cli_agent.py

Tasks:

T-3.1.1-A resume-session
- Add `sac agent resume <session_id>` that re-loads the session, re-renders the pending action, and steps the loop once when the user confirms.
- Deterministic: same fixture + same session must produce the same next action.
- Tests: new `tests/test_agent_resume.py` covering resume after `stop_for_user`, after a recoverable failure, and after a hard contract failure (must refuse to resume on hard failure).

T-3.1.1-B edit-retry-from-failure
- Add `sac edit --retry-from-last-failure` that ingests the last validator/test failure from the journal into the next prompt context.
- Failure context is redacted via the existing `redact_secrets()` path before being added.
- Tests: new `tests/test_edit_retry.py` with at least one validator-failure fixture.

Hard constraints (same as Prompt A).

After the batch:
- targeted tests: `PYTHONPATH=src python3 -m pytest tests/test_agent_resume.py tests/test_edit_retry.py -q`
- full regression: `PYTHONPATH=src python3 -m pytest -q`
- preflight: `PYTHONPATH=src python3 -m safecode.cli release preflight`
- bump to 3.1.1, version-note, matrix, SKILL.md, sync, commit, tag.
```

### Prompt C — v3.2.0 provider/LLM reliability batch

```text
You are implementing SafeCode Agent v3.2.0 (LLM retry + cost accounting)
from baseline v3.1.x.

Read first:
- .claude/skills/current/SKILL.md
- docs/product-commercialization-roadmap.md  (Section 5 v3.2.x, Section 6 tasks T-3.2.0-A and T-3.2.0-B)
- src/safecode/llm/base.py, src/safecode/llm/openai_client.py, src/safecode/llm/factory.py
- src/safecode/sandbox/network.py (network policy enforcement)
- src/safecode/agent/session.py (where session state lives)

Tasks:

T-3.2.0-A llm-retry-jitter
- Add `src/safecode/llm/retry.py` with `retry_call(fn, *, max_attempts=3, base_delay=0.5)`.
- Honor Retry-After header (seconds or HTTP-date). Add jitter (0.5-1.5x base_delay).
- Wire retry into `OpenAICompatibleLLMClient._chat`. Retry on 429, 503, and connection errors. Do NOT retry on 4xx other than 429.
- Each attempt emits a runtime-log event with attempt number and reason.
- Tests: new `tests/test_llm_retry.py` with a mock transport that simulates a sequence of failures then success.

T-3.2.0-B llm-cost-accounting
- Add `src/safecode/llm/cost.py` with a `SessionCostAccumulator` writing `.sac/sessions/<session_id>/cost.json`.
- Capture `prompt_tokens`, `completion_tokens`, `cost_usd` (None when unknown).
- Wire into `OpenAICompatibleLLMClient._chat` so every request updates the accumulator.
- `sac doctor` gains a `last_session_cost` diagnostic.
- Tests: new `tests/test_llm_cost_accounting.py` covering serialization, accumulation, and doctor output.

Hard constraints:
- All retry/cost paths must respect existing `NetworkPolicy.assert_allowed(...)`.
- No real network in tests; use mocked transports.
- Default LLM provider remains mock.
- Do not change agent contract schemas; retry must surface unrecoverable failures as `LLMContractViolation` unchanged.
- Public-contract snapshots must keep passing.

After the batch:
- targeted tests: `PYTHONPATH=src python3 -m pytest tests/test_llm_retry.py tests/test_llm_cost_accounting.py -q`
- full regression: `PYTHONPATH=src python3 -m pytest -q`
- preflight: `PYTHONPATH=src python3 -m safecode.cli release preflight`
- bump to 3.2.0, version-note, matrix, SKILL.md, sync, commit, tag.

Notes for follow-up batches:
- v3.2.1 (streaming) depends on retry landing first.
- v3.2.3 (Anthropic provider) depends on structured-output validation (v3.2.2) landing first.
- v3.2.6 promotes the provider contract to supported in `docs/public-contracts.md`. Do not promote earlier.
```
