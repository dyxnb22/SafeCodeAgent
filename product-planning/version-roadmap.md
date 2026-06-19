# SafeCodeAgent Enterprise Version Roadmap

**Implementation status (v2.0 RC):** Stages v1.0–v2.0 are implemented and
contract-frozen. Stages v2.1–v3.0 are planned (post-RC). See
`.agents/context/progress.json` for live stage state.

This roadmap is the authoritative breakdown of work for the
`dev/enterprise-agent-platform` branch. It uses two-level versions:

- **Stage versions** (`v1.0`, `v1.1`, …) define product milestones with a
  demo and an acceptance gate.
- **Sub-plans** (`v1.1.1`, `v1.1.2`, …) define work items that fit in a
  single small PR each. Every sub-plan has its own task list, files,
  tests, and acceptance criteria.

The roadmap is intentionally local-first. Every MVP step must be
demonstrable on a developer laptop with the current dependency set
(`uv`, `typer`, `pydantic`, `pytest`, mock LLM provider) plus a small
number of optional add-ons (LangGraph, a vector store, Semgrep). No
stage before `v2.0` may require a hosted service that is not optional.

> The detailed task list per sub-plan lives in
> `execution-backlog.md`. This file states the *what*; the backlog
> states the *how*.

---

## Stage Index

| Stage | Title | Demo Outcome | Hard Dependencies |
|-------|-------|--------------|-------------------|
| v1.0 | Enterprise Branch Reset and Planning | All planning docs land; enterprise namespace is reserved | none |
| v1.1 | RAG Security Knowledge Base MVP | `sac enterprise retrieve "<query>"` returns cited policy/code chunks | v1.0 |
| v1.2 | LangGraph Security Workflow MVP | A scripted workflow walks classify → retrieve → analyze → report with checkpoint resume | v1.0, v1.1 |
| v1.3 | Tool/MCP Enterprise Connector Layer | Workflow consumes a GitHub PR, a local Semgrep run, and an issue file as typed evidence | v1.2 |
| v1.4 | Security Governance, RBAC, Approval Engine | Approval inbox blocks a write action and resumes it after explicit approval | v1.2, v1.3 |
| v1.5 | AgentOps Observability and Trace Dashboard | `sac enterprise trace show <run_id>` renders a Markdown dashboard of nodes, tools, citations, approvals, cost | v1.2, v1.4 |
| v1.6 | Evaluation and Regression Platform | `pytest tests/enterprise/eval` runs deterministic eval suites with a ratchet baseline | v1.1, v1.5 |
| v1.7 | PR Security Review MVP | End-to-end: PR fixture → risk-ranked report with citations → optional draft comment behind approval | v1.3, v1.4, v1.5 |
| v1.8 | Vulnerability Remediation Workflow | Semgrep finding → fix patch proposal with checkpoint → validation → approval | v1.3, v1.4, v1.7 |
| v1.9 | Enterprise Beta Hardening | Multi-project run with policy precedence, compliance evidence export, performance budget | v1.4, v1.7, v1.8 |
| v2.0 | Enterprise Release Candidate | Public contract snapshot, external-style security review, deployment-profile docs, RC tag | v1.9 |
| v2.1 | Team Server Foundation | FastAPI Enterprise API + PostgreSQL persistence + durable worker behind the existing CLI surface; authenticated subject boundary | v2.0 |
| v2.2 | Real GitHub Secure Change Workflow | GitHub App webhook ingest → real PR read → governed comment / branch / PR create → sandboxed Semgrep + pip-audit + pytest → CI check callback, end-to-end PR review and remediation | v2.1 |
| v2.3 | Operator Console | React/Next.js read-and-approve UI over the v2.1 API; OIDC login, tenant-aware navigation, run / approval / evidence / eval / cost views | v2.1 |
| v2.4 | Enterprise Knowledge, Tickets, and Memory | PostgreSQL+pgvector persistent retrieval with incremental ingest, ACL/tenant sync, reranker, governed long-term memory, live Jira connector, secure-planning workflow | v2.1 |
| v2.5 | Production Hardening | OpenTelemetry export, durable worker recovery + DLQ, concurrency / rate / cost budgets, backups + restore, schema migration tooling, load + threat model, on-prem deploy automation | v2.2, v2.3, v2.4 |
| v3.0 | Enterprise GA | Supported public contracts, migration compatibility, signed security review, production deployment evidence, flagship demos, GA release notes | v2.5 |

---

## v1.0 Enterprise Branch Reset and Planning

**Why first:** the branch must contain only Enterprise-direction content
before any code work begins. Mixing legacy roadmaps with new ones is
the single largest source of misdirection. This stage also fixes the
namespace and test layout so every later PR drops into a known shape.

**Dependencies:** none.

**Completion demo:** a reader who has never seen the repo can read
`product-planning/` and `enterprise-docs/` and explain the target
product without consulting `main` or `archive/safecodeagent-final`.

**Blocks if missing:** every later sub-plan that needs a place to add
modules, tests, and traces.

### v1.0.1 Planning Documents (this PR)

- **Goal:** publish the complete Enterprise planning set so subsequent
  PRs only adjust details.
- **Scope:** thirteen Markdown documents under `product-planning/` and
  `enterprise-docs/`. No source code.
- **Tasks:**
  - Write the eleven new planning files listed in
    `execution-backlog.md` under section `v1.0.1`.
  - Update `product-planning/README.md` and `enterprise-docs/README.md`
    only if needed to reference the new files. (Optional in this PR;
    can defer to v1.0.2.)
- **Directories/modules:** `product-planning/`, `enterprise-docs/`.
- **New/changed tests:** none in this PR (test added in v1.0.4 verifies
  the docs exist).
- **Acceptance:**
  - All thirteen documents exist and pass Markdown lint via the
    project's existing tooling (no broken headings, no empty sections).
  - Every Stage `v1.0`–`v2.0` is described in `version-roadmap.md`.
  - Every Stage `v1.1`–`v1.4` has fully detailed sub-plans in
    `execution-backlog.md`.
- **Risks:** scope creep into design-only prose with no engineering
  hooks. Mitigation: every plan must name a file, a module, a test, or
  a CLI command.
- **Non-goals:** writing or modifying any Python code, tests, scripts,
  README, AGENTS, or `.claude` files.

### v1.0.2 Enterprise Namespace Skeleton

- **Goal:** reserve `src/safecode/enterprise/` and
  `tests/enterprise/` so later PRs have a stable home.
- **Scope:** create empty `__init__.py` files and a tiny `__about__.py`
  that exposes `__version__ = "0.0.0-dev"` so the package is
  importable. No behavior change to `sac`.
- **Tasks:**
  - Add `src/safecode/enterprise/__init__.py`.
  - Add `src/safecode/enterprise/__about__.py` exposing `__version__`.
  - Add `tests/enterprise/__init__.py` and
    `tests/enterprise/conftest.py` (empty fixtures file).
  - Add a smoke test `tests/enterprise/test_namespace_import.py`
    asserting `from safecode.enterprise import __about__` works and
    version is a non-empty string.
- **Directories/modules:** `src/safecode/enterprise/`,
  `tests/enterprise/`.
- **New/changed tests:** `tests/enterprise/test_namespace_import.py`.
- **Acceptance:**
  - `PYTHONPATH=src python3 -m pytest tests/enterprise/test_namespace_import.py -q`
    passes.
  - Full regression `PYTHONPATH=src python3 -m pytest -q` still
    passes.
  - No new CLI surface, no new public exports.
- **Risks:** accidentally exporting symbols that later become public
  contract. Mitigation: keep `__init__.py` empty.
- **Non-goals:** any feature behavior; any new dependency.

### v1.0.3 Planning Index and Cross-Linking

- **Goal:** make the docs discoverable from `product-planning/README.md`
  and `enterprise-docs/README.md`.
- **Scope:** update those two README files to list the new docs and
  link between them.
- **Tasks:**
  - Append a "Planning Files" section to
    `product-planning/README.md` listing the six new files.
  - Append a "Technical Plans" section to
    `enterprise-docs/README.md` listing the seven new files.
  - README indexes must link every new planning file (validated in
    v1.0.4-T1). Individual planning documents do not require
    back-references into their README.
- **Directories/modules:** `product-planning/`, `enterprise-docs/`.
- **New/changed tests:** none. (Index validation is part of v1.0.4.)
- **Acceptance:**
  - Both READMEs reference every planning file.
  - No file in `product-planning/` or `enterprise-docs/` is unreachable
    by following links from the two READMEs.
- **Risks:** drift between README index and actual files.
- **Non-goals:** restoring any legacy `docs/` content.

### v1.0.4 Planning Presence Test

- **Goal:** prevent silent removal of planning documents in later PRs.
- **Scope:** one pytest module that lists required planning files and
  asserts their existence and minimum line count.
- **Tasks:**
  - Add `tests/enterprise/test_planning_present.py`:
    parametrised over the thirteen filenames, asserts each file
    exists, is non-empty, and contains its required H1 title.
  - Wire the test under the deterministic local lane (mock provider).
- **Directories/modules:** `tests/enterprise/`.
- **New/changed tests:** `tests/enterprise/test_planning_present.py`.
- **Acceptance:**
  - `pytest tests/enterprise/test_planning_present.py -q` passes.
  - Removing any planning file or its top-level heading fails the
    test.
- **Risks:** brittle string match for headings. Mitigation: match the
  first non-empty H1 line, not exact slug.
- **Non-goals:** content quality checks (handled by a later linter
  pass in v1.9.4).

---

## v1.1 RAG Security Knowledge Base MVP

**Why now:** every later workflow depends on grounded citations.
Building RAG before workflow code prevents the workflow nodes from
being designed around guesswork.

**Dependencies:** v1.0.

**Completion demo:** `sac enterprise retrieve "sql injection"` against
a local policy-and-code fixture returns ranked, cited chunks with
permission verdicts. A retrieval eval suite reports baseline
precision/recall numbers.

**Blocks if missing:** v1.2 (workflow has no evidence to reason
over), v1.7 (PR review cannot ground recommendations), v1.8
(remediation has no historical-fix recall).

### v1.1.1 Source Registry and Loaders

- **Goal:** define the data model and loaders for retrieval sources
  (policy docs, code files, scanner findings, runbooks).
- **Scope:** Pydantic models for `KnowledgeSource` and source-typed
  loaders that emit normalized records.
- **Tasks:**
  - Add `src/safecode/enterprise/rag/source_registry.py` with the
    `KnowledgeSource`, `SourceType` enum, and a `SourceRegistry`
    class that loads from a YAML manifest under
    `examples/enterprise/knowledge_sources.yaml`.
  - Add loaders: `loader_markdown.py`, `loader_code.py`,
    `loader_sarif.py`, `loader_semgrep.py` under
    `src/safecode/enterprise/rag/loaders/`.
  - Each loader emits `RawRecord` objects (path, owner, type, text,
    metadata).
- **Directories/modules:** `src/safecode/enterprise/rag/`,
  `examples/enterprise/`.
- **New/changed tests:**
  - `tests/enterprise/rag/test_source_registry.py`
  - `tests/enterprise/rag/test_loader_markdown.py`
  - `tests/enterprise/rag/test_loader_sarif.py`
- **Acceptance:**
  - `SourceRegistry.from_manifest(path)` returns the four source types
    used by the fixture without network calls.
  - Loaders are deterministic on identical fixture input.
  - Unknown source types raise a typed `UnknownSourceTypeError` (no
    silent skip).
- **Risks:** SARIF schema variance. Mitigation: only support
  Semgrep-generated SARIF 2.1.0 in MVP.
- **Non-goals:** embedding, retrieval, or any UI command.

### v1.1.2 Chunking and Metadata Schema

- **Goal:** define how raw records become retrievable chunks with
  source/permission/freshness metadata.
- **Scope:** chunkers and a `Chunk` model. Reuse
  `src/safecode/index/chunker.py` where possible; do not modify it.
- **Tasks:**
  - Add `src/safecode/enterprise/rag/chunker.py` that wraps the legacy
    chunker and emits enterprise `Chunk` records with
    `chunk_id`, `source_id`, `path`, `start_line`, `end_line`,
    `source_type`, `permission_scope`, `freshness`, `hash`, and
    `metadata` dict.
  - Add `src/safecode/enterprise/rag/models.py` with the Pydantic
    `Chunk` and `Citation` models.
  - Add deterministic chunk-id generator
    `chunk_id_for(source_id, span, hash)` so repeat runs produce the
    same ids.
- **Directories/modules:** `src/safecode/enterprise/rag/`.
- **New/changed tests:**
  - `tests/enterprise/rag/test_chunker.py`
  - `tests/enterprise/rag/test_chunk_id_stability.py`
- **Acceptance:**
  - Same input file produces identical chunk ids across two runs.
  - Chunks contain non-empty `source_type`, `permission_scope`, and
    `hash`.
  - Markdown chunker preserves heading hierarchy in metadata.
- **Risks:** code chunker drift between legacy and enterprise.
  Mitigation: enterprise chunker delegates to legacy and only adds
  fields.
- **Non-goals:** embedding generation or storage.

### v1.1.3 Hybrid Retrieval and Citations

- **Goal:** turn chunks into ranked, cited results, combining keyword
  and semantic search.
- **Scope:** retriever that uses the legacy embedding store plus a
  small lexical scorer, then merges and reranks. No external vector
  database in this MVP.
- **Tasks:**
  - Add `src/safecode/enterprise/rag/retriever.py` exposing
    `HybridRetriever.retrieve(query, k, filters) -> list[Citation]`.
  - Implement keyword scoring with BM25-ish ranking over the chunk
    text (pure Python, no extra dependency unless `rank_bm25` is
    already in `pyproject.toml`; otherwise implement a minimal
    scorer).
  - Implement permission filter that drops chunks whose
    `permission_scope` is not in the actor's scope set.
  - Add a CLI command `sac enterprise retrieve` that wires the
    retriever to the standard config and prints JSON citations.
  - Cap output at `RAG_MAX_CITATIONS` (default 8). Include selection
    reason and freshness in every citation.
- **Directories/modules:** `src/safecode/enterprise/rag/`,
  `src/safecode/cli_enterprise.py` (new CLI module).
- **New/changed tests:**
  - `tests/enterprise/rag/test_hybrid_retriever.py`
  - `tests/enterprise/rag/test_permission_filter.py`
  - `tests/enterprise/rag/test_citation_shape.py`
  - `tests/enterprise/cli/test_cli_retrieve.py`
- **Acceptance:**
  - Given a fixture with two relevant policy chunks and ten unrelated
    chunks, the retriever returns the two relevant ones in top-3 with
    non-zero scores.
  - Citations include `source_id`, `score`, `selection_reason`,
    `permission_verdict`, `freshness`, `hash`.
  - Permission filter blocks restricted chunks even if their score is
    higher.
- **Risks:** quality of BM25-ish scorer on small fixtures.
  Mitigation: keep the eval threshold pragmatic and document it.
- **Non-goals:** any LLM-based reranker, any external vector DB,
  multi-tenant index isolation (v1.9.1).

### v1.1.4 Retrieval Evaluation Fixtures

- **Goal:** make retrieval quality measurable and prevent regressions.
- **Scope:** an eval suite with deterministic queries, expected
  citations, and a baseline JSON file.
- **Tasks:**
  - Add `tests/enterprise/eval/retrieval_cases/` with fixture
    queries and expected `source_id` sets.
  - Add `tests/enterprise/eval/test_retrieval_quality.py` that
    computes recall@k, MRR, and citation grounding for each case and
    compares with the ratchet baseline.
  - Add baseline file `tests/enterprise/eval/baselines/retrieval_v1_1.json`.
  - Add a CLI helper `sac enterprise eval retrieval --update-baseline`
    that writes a new baseline, intended for manual use only.
- **Directories/modules:** `tests/enterprise/eval/`,
  `src/safecode/enterprise/eval/retrieval.py`.
- **New/changed tests:** as above.
- **Acceptance:**
  - Baseline file exists and is checked in.
  - Test fails if recall@5 drops more than two percentage points
    below baseline on any case.
  - Updating the baseline requires an explicit flag; it does not
    happen automatically.
- **Risks:** flaky tests due to non-deterministic embedding output.
  Mitigation: use the mock embedding backend already in
  `src/safecode/index/embedding_backend.py` for the deterministic
  lane.
- **Non-goals:** live-provider evaluation (deferred to v1.6.5).

---

## v1.2 LangGraph Security Workflow MVP

**Why now:** with grounded retrieval available, workflow nodes can be
written against typed evidence. Designing the workflow first would
have forced retrieval shape decisions to be guessed.

**Dependencies:** v1.0, v1.1.

**Completion demo:** running
`sac enterprise workflow run --task pr_review --input fixtures/pr_001/`
executes a LangGraph state machine, persists checkpoints to
`.sac/enterprise/runs/<run_id>/state.json`, and produces a Markdown
report at `.sac/enterprise/runs/<run_id>/report.md`. The same command
with `--resume <run_id>` resumes after a simulated interrupt.

**Blocks if missing:** every later workflow (v1.7, v1.8), approvals
(v1.4), and observability (v1.5).

### v1.2.1 Workflow State Model and Node Contracts

- **Goal:** establish typed state and node contracts before any
  runtime dependency.
- **Scope:** Pydantic models defined in
  `enterprise-docs/data-models.md`. No LangGraph yet.
- **Tasks:**
  - Add `src/safecode/enterprise/workflow/state.py` with
    `EnterpriseRunState` and child models (`Plan`, `Citation`,
    `ToolCallRecord`, `ApprovalRequest`, `ValidationResult`,
    `RiskTier`, etc.).
  - Add `src/safecode/enterprise/workflow/nodes/` with one file per
    node: `classify.py`, `collect_context.py`, `retrieve.py`,
    `analyze.py`, `plan.py`, `propose.py`, `validate.py`,
    `approval.py`, `finalize.py`. Each defines an async function
    `run(state) -> NodeOutput` with a typed output model.
  - All nodes are pure stubs in this PR; behavior comes in v1.2.2.
- **Directories/modules:** `src/safecode/enterprise/workflow/`.
- **New/changed tests:**
  - `tests/enterprise/workflow/test_state_round_trip.py`
  - `tests/enterprise/workflow/test_node_contracts.py`
- **Acceptance:**
  - `EnterpriseRunState` serializes to JSON and round-trips back
    losslessly.
  - Every node module exports a `run` callable with a typed signature
    enforced by a unit test.
- **Risks:** state model becomes too large to evolve. Mitigation: use
  composition; never flatten lists of citations or tool calls into
  string fields.
- **Non-goals:** LangGraph dependency, persistence (v1.2.2), HITL
  (v1.2.4).

### v1.2.2 Local Orchestrator with Checkpoint Persistence

- **Goal:** run the nine nodes in order with a deterministic local
  orchestrator and persist state per node.
- **Scope:** a small executor that calls nodes sequentially, writes
  state checkpoints, and supports `--resume`.
- **Tasks:**
  - Add `src/safecode/enterprise/workflow/orchestrator.py` exposing
    `LocalOrchestrator.execute(state) -> EnterpriseRunState`.
  - Add `src/safecode/enterprise/workflow/checkpoint.py` that
    serializes state after each node into
    `.sac/enterprise/runs/<run_id>/state.json` and
    `.../node_<n>_<name>.json` for diagnostics.
  - Add `sac enterprise workflow run` CLI that takes a task type and
    fixture path and invokes the orchestrator.
  - Implement node stubs that produce deterministic output for the
    `mock` LLM provider so tests do not need a network call.
- **Directories/modules:** `src/safecode/enterprise/workflow/`,
  `src/safecode/cli_enterprise.py`.
- **New/changed tests:**
  - `tests/enterprise/workflow/test_orchestrator_happy_path.py`
  - `tests/enterprise/workflow/test_orchestrator_resume.py`
  - `tests/enterprise/cli/test_cli_workflow_run.py`
- **Acceptance:**
  - Happy-path test runs all nine nodes against a fixture and
    produces a non-empty final report stub.
  - Resume test starts a run, simulates an interrupt after
    `plan_actions`, then re-invokes `--resume <run_id>` and finishes
    without re-running prior nodes.
  - Checkpoints are under `.sac/enterprise/runs/<run_id>/` and
    cleaned by an explicit `sac enterprise workflow gc` command (not
    automatic).
- **Risks:** state mutability bugs between nodes. Mitigation: nodes
  return immutable patches that the orchestrator applies.
- **Non-goals:** LangGraph integration (v1.2.3), HITL (v1.2.4),
  branch conditions beyond linear order (v1.2.3).

### v1.2.3 LangGraph Runtime Wiring

- **Goal:** swap the local orchestrator's traversal for LangGraph
  `StateGraph` while keeping the same node contracts.
- **Scope:** an adapter that constructs a `StateGraph` from the
  existing nodes and conditional edges.
- **Tasks:**
  - Add `langgraph` to `pyproject.toml` as an optional dependency
    under an `enterprise` extra. Do not make it a hard dependency.
  - Add `src/safecode/enterprise/workflow/graph.py` building the
    `StateGraph` and conditional edges (missing-evidence,
    high-risk-action, validation-failure, user-rejection).
  - Add `EnterpriseRunState` reducer wrappers so LangGraph can
    process patches.
  - Switch the orchestrator to LangGraph behind a feature flag
    `WORKFLOW_RUNTIME=langgraph|local`. Default `local` in tests.
- **Directories/modules:** `src/safecode/enterprise/workflow/`,
  `pyproject.toml` (add optional extra).
- **New/changed tests:**
  - `tests/enterprise/workflow/test_graph_topology.py`
  - `tests/enterprise/workflow/test_graph_conditional_edges.py`
  - Reuse the existing happy-path and resume tests under both runtime
    flags.
- **Acceptance:**
  - With `WORKFLOW_RUNTIME=langgraph`, all existing workflow tests
    pass.
  - Graph topology test asserts the expected node set and
    conditional-edge set.
  - Local orchestrator remains the deterministic default for unit
    tests.
- **Risks:** LangGraph API drift between minor versions. Mitigation:
  pin a known-good `langgraph` minor; document in
  `enterprise-docs/system-architecture-v1.md`.
- **Non-goals:** distributed execution; persistent LangGraph
  checkpointers backed by a database.

### v1.2.4 Human-in-the-Loop Interrupt and Resume

- **Goal:** allow the workflow to pause for human approval and
  resume exactly where it paused.
- **Scope:** an `interrupt` node primitive plus an `ApprovalRequest`
  store backed by `.sac/enterprise/approvals/`.
- **Tasks:**
  - Add `src/safecode/enterprise/workflow/interrupt.py` exposing
    `pause_for_approval(state, request)` that writes an
    `ApprovalRequest` and raises a typed `WorkflowInterrupted` error
    caught by the CLI.
  - Add `sac enterprise approval list/show/approve/reject` CLI
    commands. Approvals are written by a separate user, not by the
    model.
  - Update the `approval_gate` node so that high-risk plans always
    pause; low-risk plans never pause.
  - Implement resume: re-running the workflow with `--resume`
    detects pending approvals and either continues or aborts based
    on the decision.
- **Directories/modules:** `src/safecode/enterprise/workflow/`,
  `src/safecode/enterprise/approvals/`,
  `src/safecode/cli_enterprise.py`.
- **New/changed tests:**
  - `tests/enterprise/workflow/test_approval_interrupt.py`
  - `tests/enterprise/cli/test_cli_approval_flow.py`
- **Acceptance:**
  - A high-risk fixture stops at `approval_gate` and writes an
    `ApprovalRequest`.
  - Running `sac enterprise approval reject <id>` followed by
    `workflow run --resume <run_id>` finishes the run in a
    "rejected" terminal state without executing the write action.
  - Approving and resuming executes the gated action.
- **Risks:** approval store path collisions across runs. Mitigation:
  one directory per `run_id` and per `approval_id`.
- **Non-goals:** RBAC enforcement on the approval action (v1.4.4);
  real GitHub write (v1.3.2 / v1.7.3).

---

## v1.3 Tool/MCP Enterprise Connector Layer

**Why now:** the workflow MVP is done but operates on fixtures.
Connectors turn fixtures into real PRs, issues, and scanner runs
while keeping every existing safety gate intact.

**Dependencies:** v1.2.

**Completion demo:** the workflow consumes a real GitHub PR (via the
existing `github_read_tools`), a local Semgrep run, and an issue
loaded from a Markdown fixture. Each call appears in the trace with
typed evidence and a redaction record.

**Blocks if missing:** v1.7 (PR review needs PR read), v1.8 (remediation
needs scanner input), v1.4.5 (audit taxonomy needs concrete events to
classify).

### v1.3.1 Tool Metadata Schema and Enterprise Tool Registry

- **Goal:** make every tool's category, approval tier, and audit type
  visible to the workflow before it is called.
- **Scope:** a registry that maps tool names to enterprise metadata.
  Native tools and MCP tools are both registered through the same
  surface.
- **Tasks:**
  - Add `src/safecode/enterprise/tools/registry.py` exposing
    `ToolRegistry`, `ToolSpec`, and `register_native(spec)`.
  - Pre-register existing native tool spec wrappers for
    `read_file`, `search`, `command`, `github_read`,
    `github_write`, `web_fetch`. Read the legacy spec from
    `src/safecode/agent/native_tools.py` (don't modify it); copy
    only the fields needed.
  - Define `ApprovalTier = Literal['AUTO', 'CONFIRM', 'GATE', 'BLOCK']`
    on `ToolSpec`.
- **Directories/modules:** `src/safecode/enterprise/tools/`.
- **New/changed tests:**
  - `tests/enterprise/tools/test_registry_round_trip.py`
  - `tests/enterprise/tools/test_native_tool_specs_present.py`
- **Acceptance:**
  - All six native tools listed above appear in the registry.
  - Unknown tool name lookup returns `None` (not a crash).
  - Approval tier is `BLOCK` for any tool not explicitly registered.
- **Risks:** divergence between legacy and enterprise tool specs.
  Mitigation: enterprise registry imports legacy spec data but does
  not redefine it.
- **Non-goals:** any MCP discovery (v1.3.5).

### v1.3.2 GitHub PR Read Connector Hardening

- **Goal:** make the existing GitHub PR read tool usable as a
  workflow node with typed PR evidence.
- **Scope:** an enterprise-side adapter over
  `src/safecode/agent/github_read_tools.py`. No modifications to the
  underlying tool.
- **Tasks:**
  - Add `src/safecode/enterprise/connectors/github_pr.py` exposing
    `fetch_pr(spec) -> PullRequestEvidence`.
  - Add a `PullRequestEvidence` Pydantic model with title, body,
    files, diff hunks, base/head refs, author, labels, and reviewer
    list.
  - Add redaction step that drops `Authorization` headers and any
    `X-GitHub-Token` echoes in error fields.
  - Wire it into the `collect_repo_context` workflow node when the
    task type is `pr_review`.
- **Directories/modules:** `src/safecode/enterprise/connectors/`.
- **New/changed tests:**
  - `tests/enterprise/connectors/test_github_pr_evidence.py`
  - `tests/enterprise/connectors/test_github_pr_redaction.py`
- **Acceptance:**
  - Evidence object includes diff hunks with stable IDs.
  - Redaction test asserts no string matching `gh[ps]_[A-Za-z0-9]{30,}`
    survives in evidence or error fields.
  - Connector works in offline mode against a recorded fixture JSON.
- **Risks:** rate-limit handling for live calls.
  Mitigation: connector is offline-by-default; live mode is opt-in
  through the existing network policy gate.
- **Non-goals:** PR write (v1.7.3).

### v1.3.3 Issue Tracker Connector

- **Goal:** ingest a security ticket as typed evidence.
- **Scope:** a Markdown-fixture and Jira-shaped JSON loader. No live
  Jira/Linear API in MVP.
- **Tasks:**
  - Add `src/safecode/enterprise/connectors/issue.py` exposing
    `fetch_issue(spec) -> IssueEvidence`.
  - Support two source kinds: `markdown` (local file) and
    `jira_json` (saved API payload).
  - Normalize fields: id, title, body, labels, severity, reporter,
    linked PRs.
- **Directories/modules:** `src/safecode/enterprise/connectors/`.
- **New/changed tests:**
  - `tests/enterprise/connectors/test_issue_markdown.py`
  - `tests/enterprise/connectors/test_issue_jira_json.py`
- **Acceptance:**
  - Both source kinds produce identical `IssueEvidence` shape.
  - Missing severity defaults to `unknown` rather than raising.
- **Risks:** ticket bodies contain prompt-injection text.
  Mitigation: handled by the prompt-injection eval in v1.6.3 and the
  retriever's content-not-instruction rule.
- **Non-goals:** writing comments back to a ticket (v1.4.3 approval
  flow + v2.0 connector).

### v1.3.4 Scanner Integration: Semgrep and Dependency Audit

- **Goal:** make Semgrep and `pip-audit` outputs first-class evidence.
- **Scope:** a normalizer that turns raw JSON into typed
  `SecurityFinding` objects.
- **Tasks:**
  - Add `src/safecode/enterprise/scanners/semgrep.py` and
    `src/safecode/enterprise/scanners/pip_audit.py`.
  - Both expose `normalize(raw_json) -> list[SecurityFinding]`.
  - `SecurityFinding` defined in `enterprise-docs/data-models.md` and
    implemented in `src/safecode/enterprise/scanners/models.py`.
  - Add an offline mode that reads from a fixture; live mode runs
    the local CLI through the existing sandbox proposal pipeline.
- **Directories/modules:** `src/safecode/enterprise/scanners/`.
- **New/changed tests:**
  - `tests/enterprise/scanners/test_semgrep_normalize.py`
  - `tests/enterprise/scanners/test_pip_audit_normalize.py`
  - `tests/enterprise/scanners/test_scanner_invocation_is_proposal.py`
- **Acceptance:**
  - Offline fixtures normalize to deterministic `SecurityFinding`
    lists with stable `finding_id`s.
  - Live scanner execution refuses to run unless a sandbox proposal
    is approved (existing gate).
  - Unsupported scanner output raises `UnsupportedScannerVersionError`
    instead of silently producing partial findings.
- **Risks:** Semgrep schema changes between versions. Mitigation:
  declare a single supported schema version per scanner and document
  it.
- **Non-goals:** networked SAST APIs (deferred to v2.0).

### v1.3.5 MCP Connector Wrapper with Capability Scopes

- **Goal:** expose MCP discovery and read tools to workflows behind
  the enterprise tool registry, with redaction and capability scoping.
- **Scope:** adapter over `src/safecode/mcp/` that wraps discovery and
  the read-only runner into the registry.
- **Tasks:**
  - Add `src/safecode/enterprise/connectors/mcp_adapter.py` exposing
    `register_mcp_tools(registry, server_id)`.
  - Adapter calls the existing discovery in `src/safecode/mcp/discovery.py`
    (no modification).
  - Static reclassification: server-claimed `category` is *ignored*.
    Enterprise classification defaults to `BLOCK` unless an
    operator-supplied YAML allowlist permits `AUTO` or `CONFIRM`.
  - Outputs run through the existing MCP redactor and size cap.
- **Directories/modules:** `src/safecode/enterprise/connectors/`.
- **New/changed tests:**
  - `tests/enterprise/connectors/test_mcp_registration.py`
  - `tests/enterprise/connectors/test_mcp_server_classification_ignored.py`
  - `tests/enterprise/connectors/test_mcp_output_redaction.py`
- **Acceptance:**
  - An MCP server that claims `category: write` is still treated as
    `BLOCK` unless the local allowlist overrides.
  - Output size limits enforced (4 KB default per call).
  - Tool name collisions across servers are namespaced
    (`mcp:<server_id>:<tool>`).
- **Risks:** prompt-injection through MCP responses. Mitigation:
  treated as content; covered by v1.6.3 prompt-injection eval.
- **Non-goals:** MCP write tools (defer to v1.9 once approval engine
  is mature).

---

## v1.4 Security Governance, RBAC, Approval Engine

**Why now:** with multiple tool and connector types now executing,
the approval gate from v1.2.4 needs a policy and RBAC layer behind it
before it can be trusted for branch pushes or PR creation.

**Dependencies:** v1.2, v1.3.

**Completion demo:** a workflow that proposes a file write requests an
approval, the approval is denied because the user lacks the
`maintainer` role, and the audit log contains a "policy_block" event
with reason and snapshot of the active policy.

**Blocks if missing:** v1.7 (PR comment creation needs gated
approval), v1.8 (patch apply needs RBAC), v1.9 (compliance evidence
needs taxonomy).

### v1.4.1 Policy Precedence Chain

- **Goal:** load and merge policies in the order organization > user >
  project > environment > workflow-specific, with lower layers unable
  to weaken upper ones.
- **Scope:** a `PolicyResolver` that produces a `PolicySnapshot` for a
  run.
- **Tasks:**
  - Add `src/safecode/enterprise/policy/resolver.py` and
    `src/safecode/enterprise/policy/models.py` (`Policy`,
    `PolicySnapshot`).
  - Sources: `~/.config/safecode/enterprise/org.yaml`,
    `~/.config/safecode/enterprise/user.yaml`,
    `<repo>/.sac/enterprise/project.yaml`, env vars prefixed
    `SAC_ENTERPRISE_`, and per-workflow overrides passed by the CLI.
  - Implement "no weakening" rule: a lower-layer key may not change a
    value from `BLOCK` to `AUTO`. Tested with explicit cases.
- **Directories/modules:** `src/safecode/enterprise/policy/`.
- **New/changed tests:**
  - `tests/enterprise/policy/test_resolver_precedence.py`
  - `tests/enterprise/policy/test_no_weakening.py`
- **Acceptance:**
  - With only an org policy present, the snapshot reflects org keys.
  - With project policy attempting to set `github_write` to `AUTO`
    while org policy says `GATE`, snapshot keeps `GATE` and emits a
    `policy.project_override_blocked` event.
- **Risks:** confusion between "default" and "block" semantics.
  Mitigation: every key has an explicit enum value; no `null` means
  permissive.
- **Non-goals:** policy editing UI; remote policy distribution.

### v1.4.2 RBAC Subject and Roles

- **Goal:** decide which actions an actor can take or approve.
- **Scope:** an `RBACSubject` resolved from the active CLI session
  plus a static role-to-permission map.
- **Tasks:**
  - Add `src/safecode/enterprise/rbac/models.py` with `RBACSubject`
    and `Role` enum (`viewer`, `developer`, `security_reviewer`,
    `maintainer`, `platform_admin`).
  - Add `src/safecode/enterprise/rbac/permissions.py` defining the
    role-to-action map (see `security-governance-plan.md` action
    matrix).
  - Roles are read from the user-level policy file. CLI flag
    `--as-role` is allowed only when org policy permits it.
- **Directories/modules:** `src/safecode/enterprise/rbac/`.
- **New/changed tests:**
  - `tests/enterprise/rbac/test_role_to_permission_map.py`
  - `tests/enterprise/rbac/test_as_role_flag_blocked.py`
- **Acceptance:**
  - Permission matrix matches `security-governance-plan.md`.
  - `--as-role platform_admin` is rejected if org policy does not
    allow it.
- **Risks:** missing default role on first run. Mitigation: default
  is `developer`; explicit warning when no user policy file exists.
- **Non-goals:** SSO/LDAP integration.

### v1.4.3 Approval Tier Engine and Grant Store

- **Goal:** turn the v1.2.4 approval primitive into a tier engine
  that selects AUTO/CONFIRM/GATE/BLOCK based on policy + RBAC + tool
  spec.
- **Scope:** decision function + a per-run grant store.
- **Tasks:**
  - Add `src/safecode/enterprise/approvals/engine.py` exposing
    `decide(action, policy, rbac, tool_spec) -> ApprovalDecision`.
  - Add `src/safecode/enterprise/approvals/store.py` for persistent
    grants, including single-use semantics.
  - Update the `approval_gate` node to use the engine.
- **Directories/modules:** `src/safecode/enterprise/approvals/`.
- **New/changed tests:**
  - `tests/enterprise/approvals/test_decision_matrix.py`
  - `tests/enterprise/approvals/test_grant_single_use.py`
  - `tests/enterprise/approvals/test_decision_with_rbac.py`
- **Acceptance:**
  - Decision matrix tests cover all `action × role × tool spec`
    combinations listed in `security-governance-plan.md`.
  - A grant cannot be consumed twice; second use raises
    `GrantAlreadyConsumedError`.
  - Decisions reference the resolved `policy_snapshot_id`.
- **Risks:** matrix explosion. Mitigation: the matrix is encoded in
  one Pydantic table-of-rows that the tests load directly.
- **Non-goals:** time-bound grants (deferred to v1.9).

### v1.4.4 Approval Inbox CLI Surface

- **Goal:** make pending approvals discoverable and actionable from
  the CLI.
- **Scope:** richer `sac enterprise approval` commands.
- **Tasks:**
  - Extend v1.2.4 commands: `list --pending`, `show <id>`,
    `approve <id> [--note]`, `reject <id> [--reason]`,
    `request-evidence <id>`, and `revoke <id>` (for not-yet-consumed
    grants).
  - Add a Markdown render of pending approvals.
- **Directories/modules:** `src/safecode/cli_enterprise.py`,
  `src/safecode/enterprise/approvals/cli_render.py`.
- **New/changed tests:**
  - `tests/enterprise/cli/test_cli_approval_render.py`
  - `tests/enterprise/cli/test_cli_approval_revoke.py`
- **Acceptance:**
  - `sac enterprise approval list --pending` shows id, action, risk
    tier, requesting workflow, requested-by user, and age.
  - Reject reason is required when policy demands evidence.
- **Risks:** UX confusion between "approve" and "grant".
  Mitigation: tightly worded help strings and a doc section in
  `enterprise-docs/security-governance-plan.md`.
- **Non-goals:** web UI inbox (v1.9.4 or later).

### v1.4.5 Audit Event Taxonomy

- **Goal:** define the audit event types the workflow emits.
- **Scope:** an `AuditTraceEvent` schema and a taxonomy table.
- **Tasks:**
  - Add `src/safecode/enterprise/audit/events.py` mapping every
    workflow-level event to a typed Pydantic class. Reuse the legacy
    hash-chain logger in `src/safecode/audit/logger.py` (no
    modification).
  - Add the taxonomy table to
    `enterprise-docs/security-governance-plan.md` (the doc lives in
    v1.0.1; v1.4.5 fills the implementation pointers).
  - Emit events from every workflow node and approval engine.
- **Directories/modules:** `src/safecode/enterprise/audit/`.
- **New/changed tests:**
  - `tests/enterprise/audit/test_taxonomy_coverage.py`
  - `tests/enterprise/audit/test_hash_chain_intact.py`
- **Acceptance:**
  - Every event class is referenced by at least one node or engine
    in `src/safecode/enterprise/`.
  - Hash-chain check passes on a workflow run.
- **Risks:** event explosion. Mitigation: cap at the taxonomy table
  in v1.0.1; new event types require updating that table first.
- **Non-goals:** external audit shipping (v2.0).

---

## v1.5 AgentOps Observability and Trace Dashboard

**Why now:** by v1.4 a workflow can run, gate actions, and audit
itself. The remaining gap is making that visible to a human who did
not run the workflow.

**Dependencies:** v1.2, v1.4.

**Completion demo:** `sac enterprise trace show <run_id>` renders a
Markdown report with node timeline, model and tool calls (redacted),
retrieval citations with permission verdicts, approval events, cost,
token use, latency, and failure category.

**Blocks if missing:** v1.6 (eval cannot compare runs without
serialized traces), v1.9 (compliance evidence depends on trace
export).

### v1.5.1 Trace Event Schema and Emitter

- **Goal:** define a trace event Pydantic model used by every node,
  tool, and approval surface.
- **Scope:** `TraceEvent` and an `Emitter` interface.
- **Tasks:**
  - Add `src/safecode/enterprise/trace/events.py` with `TraceEvent`,
    `TraceEventType` enum, and a `TraceContext` dataclass that nodes
    can pass around.
  - Add `src/safecode/enterprise/trace/emitter.py` with file-backed
    emitter writing `.sac/enterprise/runs/<run_id>/trace.jsonl`.
  - Wire emitter into workflow orchestrator and approval engine.
- **Directories/modules:** `src/safecode/enterprise/trace/`.
- **New/changed tests:**
  - `tests/enterprise/trace/test_event_schema.py`
  - `tests/enterprise/trace/test_emitter_idempotency.py`
- **Acceptance:**
  - Every event has `run_id`, `node_id`, `timestamp`, `type`,
    `payload`, and `redaction_applied`.
  - Re-running an emitter does not duplicate events for the same
    `event_id`.
- **Risks:** trace file grows unbounded. Mitigation: cap individual
  payloads (e.g. tool output preview ≤ 2 KB).
- **Non-goals:** OpenTelemetry export (v2.0 candidate).

### v1.5.2 Run Timeline JSON Serializer

- **Goal:** produce a canonical JSON form of a run that downstream
  tools (dashboard, eval) can consume.
- **Scope:** a serializer that joins state checkpoints, trace
  events, and approval records into a single
  `.sac/enterprise/runs/<run_id>/timeline.json`.
- **Tasks:**
  - Add `src/safecode/enterprise/trace/timeline.py`.
  - Define the timeline schema (nodes, model calls, tool calls,
    retrievals, approvals, costs, validation outcomes, failure
    summary). Schema lives in
    `enterprise-docs/agentops-observability-plan.md` and is
    implemented here.
  - Add a CLI command `sac enterprise trace export <run_id> --json`.
- **Directories/modules:** `src/safecode/enterprise/trace/`.
- **New/changed tests:**
  - `tests/enterprise/trace/test_timeline_round_trip.py`
  - `tests/enterprise/trace/test_timeline_redaction.py`
- **Acceptance:**
  - Two consecutive serializations of the same run produce identical
    JSON.
  - Sensitive fields (raw prompts, full file contents) are absent or
    explicitly marked `"redacted": true`.
- **Risks:** schema becomes brittle as features change.
  Mitigation: version the schema with `timeline_schema_version`
  field.
- **Non-goals:** binary export format; live streaming.

### v1.5.3 Markdown Dashboard Renderer

- **Goal:** render the timeline as a human-readable Markdown report.
- **Scope:** a renderer plus the CLI command `sac enterprise trace
  show`.
- **Tasks:**
  - Add `src/safecode/enterprise/trace/render_markdown.py` producing
    sections: Summary, Timeline, Citations, Tool Calls, Approvals,
    Validation, Cost, Safety Invariants, Failures.
  - Add CLI command `sac enterprise trace show <run_id>` that writes
    Markdown to stdout or a file.
- **Directories/modules:** `src/safecode/enterprise/trace/`,
  `src/safecode/cli_enterprise.py`.
- **New/changed tests:**
  - `tests/enterprise/trace/test_render_markdown_sections.py`
  - `tests/enterprise/cli/test_cli_trace_show.py`
- **Acceptance:**
  - Rendered Markdown contains all sections listed above.
  - Citations include source path, line range, score, and permission
    verdict.
- **Risks:** Markdown drift from JSON schema. Mitigation: renderer
  reads only the timeline JSON, not raw events.
- **Non-goals:** web UI (later).

### v1.5.4 Redaction Policy for Trace Export

- **Goal:** make trace export safe to share by default.
- **Scope:** a redaction layer applied at write time and at export
  time.
- **Tasks:**
  - Add `src/safecode/enterprise/trace/redaction.py` reusing the
    legacy redactor in `src/safecode/context/redactor.py`.
  - Add a config flag `trace.export.profile = {strict|standard|debug}`
    in the policy schema. Default `strict`.
  - In `strict`, raw model prompts and complete file contents are
    never written. In `debug`, they are written but require an
    explicit policy bit `allow_debug_traces=true`.
- **Directories/modules:** `src/safecode/enterprise/trace/`,
  `src/safecode/enterprise/policy/`.
- **New/changed tests:**
  - `tests/enterprise/trace/test_redaction_strict_default.py`
  - `tests/enterprise/trace/test_redaction_debug_requires_policy.py`
- **Acceptance:**
  - In strict mode no field of length > 2 KB appears verbatim.
  - Switching to debug mode without policy bit raises
    `DebugTraceNotAllowed`.
- **Risks:** debug-mode artifacts leaking in eval bundles.
  Mitigation: eval lane forces strict.
- **Non-goals:** customer-supplied redaction patterns (v1.9).

---

## v1.6 Evaluation and Regression Platform

**Why now:** with workflow, approvals, and traces in place, eval can
finally measure real workflow behavior, not just retrieval.

**Dependencies:** v1.1, v1.5.

**Completion demo:** `pytest tests/enterprise/eval -q` runs the four
eval suites (retrieval, prompt-injection, MCP/tool classification
attacks, PR review baseline) and updates a Markdown dashboard at
`.sac/enterprise/eval/latest.md`. Ratchet failures block merges in
CI.

**Blocks if missing:** v1.7 (PR review needs measurable baseline),
v2.0 (release evidence needs eval dashboards).

### v1.6.1 Eval Case Schema and Runner

- **Goal:** make `EvaluationCase` and `EvaluationResult` typed and
  runnable.
- **Scope:** runner + dataset loader.
- **Tasks:**
  - Add `src/safecode/enterprise/eval/cases.py` with
    `EvaluationCase` and `EvaluationResult` Pydantic models.
  - Add `src/safecode/enterprise/eval/runner.py` that runs a case
    against the workflow with the mock LLM and produces a
    `EvaluationResult`.
  - Add dataset discovery from `tests/enterprise/eval/cases/`.
- **Directories/modules:** `src/safecode/enterprise/eval/`.
- **New/changed tests:**
  - `tests/enterprise/eval/test_runner_round_trip.py`
- **Acceptance:**
  - A trivial pass-through case runs to completion in <2 s.
  - Case ids are unique; duplicates raise `DuplicateCaseIdError`.
- **Risks:** runner becomes coupled to workflow internals.
  Mitigation: case interacts with the workflow only through CLI
  flags + state file.
- **Non-goals:** live provider eval (v1.6.5 documents path; v1.9.x
  may execute).

### v1.6.2 Retrieval Eval Suite

- **Goal:** lift v1.1.4 retrieval eval into the new case schema.
- **Tasks:**
  - Move retrieval cases under `tests/enterprise/eval/cases/retrieval/`.
  - Add new cases: policy retrieval, code localization, stale
    document detection, citation grounding.
- **Acceptance:**
  - Cases reference baseline metrics; runner compares results.
- **Risks:** none beyond v1.1.4.
- **Non-goals:** none.

### v1.6.3 Prompt-Injection Eval Suite

- **Goal:** measure the agent's resistance to injection text from
  retrieval, MCP, ticket bodies, and scanner messages.
- **Tasks:**
  - Add `tests/enterprise/eval/cases/prompt_injection/` with at
    least eight cases: ignore-policy, reveal-secret,
    run-command, push-branch, redact-evidence, change-approval,
    change-policy, masquerade-as-policy.
  - Cases assert the workflow's final report contains an explicit
    "injection-detected" tag and refuses the embedded instruction.
- **Acceptance:**
  - All cases pass under the mock provider.
- **Non-goals:** non-English injection text (v1.9).

### v1.6.4 Tool-Classification Adversarial Suite

- **Goal:** verify that MCP and tool classification cannot be
  changed by server-supplied data.
- **Tasks:**
  - Add `tests/enterprise/eval/cases/tool_classification/` with
    cases where MCP servers claim write tools are read-only, or
    where tool spec metadata in MCP discovery is malformed.
- **Acceptance:**
  - All adversarial cases result in either `BLOCK` decisions or
    typed errors. No accidental upgrades to `AUTO`.
- **Non-goals:** native-tool spoofing (no in-process attack model).

### v1.6.5 Eval Ratchet and Dashboard

- **Goal:** turn eval results into a tracked baseline and a Markdown
  dashboard.
- **Tasks:**
  - Add `src/safecode/enterprise/eval/dashboard.py` that writes
    `.sac/enterprise/eval/latest.md`.
  - Add baselines under `tests/enterprise/eval/baselines/`.
  - Add CLI `sac enterprise eval run --suite all/retrieval/...`.
- **Acceptance:**
  - Dashboard contains a table per suite with pass/fail and metric
    deltas.
  - Baselines change only via explicit `--update-baseline`.
- **Risks:** baseline rot. Mitigation: every baseline file lists the
  date and the commit that produced it.
- **Non-goals:** web dashboard (later).

---

## v1.7 PR Security Review MVP

**Why now:** the user-facing flagship demo. With workflow, tools,
RBAC, approvals, traces, and eval in place, PR review becomes the
first end-to-end product demo.

**Dependencies:** v1.3, v1.4, v1.5.

**Completion demo:** given a PR fixture (or a live PR URL with
network policy enabled), the workflow produces a risk-ranked report
with citations, a draft comment, and (optionally, behind approval) a
posted PR comment.

**Blocks if missing:** demo + interview value; v1.8 reuses many
nodes.

### v1.7.1 PR Review Workflow Nodes

- **Tasks:** specialize `classify_request`, `collect_repo_context`,
  `retrieve_policy_and_code`, `analyze_security_risk`, and
  `propose_report_or_patch` for the PR review task type. Add a
  `pr_review` sub-graph in
  `src/safecode/enterprise/workflow/tasks/pr_review.py`.
- **Tests:** `tests/enterprise/workflow/tasks/test_pr_review_happy_path.py`.
- **Acceptance:** workflow consumes a PR fixture and emits a risk-tier
  report with at least one cited policy and at least one cited code
  span when the fixture contains a known SQL-injection pattern.

### v1.7.2 Risk-Ranked Report Renderer

- **Tasks:** add `src/safecode/enterprise/workflow/render_pr_report.py`
  emitting a Markdown report with sections: Summary, Risk Findings
  (sorted high → low), Cited Policies, Cited Code, Suggested Patch
  (if any), Trace References.
- **Tests:** `tests/enterprise/workflow/test_pr_report_render.py`.
- **Acceptance:** report contains all sections; risk findings include
  severity, location, evidence, and policy citation.

### v1.7.3 GitHub PR Comment Writer with Approval Gate

- **Tasks:** add `src/safecode/enterprise/connectors/github_pr_write.py`
  posting a draft comment. Routed through the approval engine and the
  legacy github write tool with no shell strings.
- **Tests:** `tests/enterprise/connectors/test_github_pr_comment_gated.py`.
- **Acceptance:** without approval, no network call is made; with
  approval, the call is recorded and the trace contains a
  `tool.github_write` event with redacted body.

### v1.7.4 PR Review Eval Suite

- **Tasks:** add `tests/enterprise/eval/cases/pr_review/` with at
  least five cases: SQL-injection diff, hardcoded secret addition,
  insecure deserialization diff, dependency-upgrade with CVE,
  benign change.
- **Acceptance:** every case has expected findings and forbidden
  behaviors; suite passes under the mock provider.

---

## v1.8 Vulnerability Remediation Workflow

**Why now:** the second flagship demo, extending the PR-review
workflow with a patch-proposal path.

**Dependencies:** v1.3, v1.4, v1.7.

**Completion demo:** Semgrep finding → vulnerable code located →
patch proposal with diff preview → checkpoint → approval → patch
applied → revalidation → final report.

### v1.8.1 Finding Ingestion (SARIF + Semgrep JSON)

- **Tasks:** add `src/safecode/enterprise/workflow/tasks/remediation.py`
  ingesting SARIF and Semgrep JSON via v1.3.4 normalizers.
- **Tests:** `tests/enterprise/workflow/tasks/test_remediation_ingest.py`.
- **Acceptance:** the `collect_repo_context` node returns
  `SecurityFinding[]` and a relevant code-chunk list.

### v1.8.2 Vulnerability Classifier and Fix Planner

- **Tasks:** add LLM-backed nodes (mock-friendly) that map findings
  to vulnerability types and propose minimal fixes referencing the
  cited policy.
- **Tests:** `tests/enterprise/workflow/tasks/test_remediation_classifier.py`.
- **Acceptance:** for known fixture findings, the proposed plan
  references the matching policy citation.

### v1.8.3 Patch Proposal with Checkpoint and Rollback

- **Tasks:** wire the patch proposal through the existing legacy
  `checkpoint` and `patch` modules. No legacy code change; an
  adapter writes the proposed diff and creates a checkpoint before
  apply.
- **Tests:** `tests/enterprise/workflow/test_patch_rollback.py`.
- **Acceptance:** on rejection or validation failure, rollback
  returns the working tree to the pre-patch state, verified by hash.

### v1.8.4 Validation Node (Rerun Tests and Scanners)

- **Tasks:** add a validation node that runs project tests and
  re-runs Semgrep on the patched file set through the sandbox
  proposal pipeline.
- **Tests:** `tests/enterprise/workflow/test_validation_rerun.py`.
- **Acceptance:** validation report includes test outcomes and a
  scanner diff (new vs cleared findings).

### v1.8.5 Remediation Eval Suite

- **Tasks:** add five remediation cases covering common Semgrep
  findings. Forbidden behaviors include patching unrelated files
  and disabling tests.
- **Acceptance:** baseline pass rate published; ratchet enforced.

---

## v1.9 Enterprise Beta Hardening

**Why now:** features are present; quality and operability gaps need
to close before declaring beta.

**Dependencies:** v1.4, v1.7, v1.8.

**Completion demo:** two-project run with separate tenant boundaries,
compliance evidence export, performance budget pass.

### v1.9.1 Multi-Project Namespace and Tenant Boundary

- **Tasks:** introduce `tenant_id` on `RBACSubject`, `PolicySnapshot`,
  retrieval indexes, and traces. Tenant filters wired into RAG and
  audit logs.
- **Tests:** `tests/enterprise/multitenant/test_tenant_isolation.py`,
  `tests/enterprise/multitenant/test_retrieval_tenant_filter.py`.
- **Acceptance:** a query in tenant A never retrieves chunks owned
  by tenant B, even if the chunk content matches.

### v1.9.2 Compliance Evidence Export

- **Tasks:** add `sac enterprise evidence export --run <id>` producing
  a zip with redacted trace, citation list, approval records, audit
  chain, and validation outputs.
- **Tests:** `tests/enterprise/evidence/test_export_shape.py`.
- **Acceptance:** export passes a hash-chain check on import.

### v1.9.3 Performance Regression Budget

- **Tasks:** add latency budgets per node and per workflow. Eval
  dashboard flags regressions.
- **Tests:** `tests/enterprise/perf/test_workflow_latency_budget.py`.
- **Acceptance:** PR review under fixture finishes < 30 s on mock
  provider on the CI machine.

### v1.9.4 Documentation Pass for Beta

- **Tasks:** review every doc under `product-planning/` and
  `enterprise-docs/`. Add a "Status" line to each doc indicating its
  implementation coverage as of `v1.9`. (This is a doc-only PR but a
  large one; can be split.)
- **Acceptance:** every doc shows current implementation status.

---

## v2.0 Enterprise Release Candidate

**Why last:** RC means contracts are frozen and external review
happened.

**Dependencies:** v1.9.

**Completion demo:** tagged RC build with public contract snapshot,
external-style security review notes, deployment-profile docs,
release dashboard.

### v2.0.1 Public Contract Snapshot

- **Tasks:** freeze the public surface (`sac enterprise` CLI commands,
  trace JSON schema, evidence-export schema, eval baseline format).
  Add `tests/enterprise/contracts/test_public_contract_v2_0.py`.
- **Acceptance:** any change to listed contract files triggers a
  snapshot mismatch.

### v2.0.2 External-Style Security Review

- **Tasks:** run `/code-review ultra` on the entire branch; document
  findings and fixes in `enterprise-docs/security-review-v2-0.md`.
- **Acceptance:** all high-severity findings closed or accepted with
  written rationale.

### v2.0.3 Deployment Profile Docs

- **Tasks:** add `enterprise-docs/deployment-profiles.md` covering
  local single-user, team server, and on-prem hybrid. Plans only;
  implementation may follow later.
- **Acceptance:** each profile explains components, security
  posture, dependencies, and known limitations.

### v2.0.4 RC Tag and Release Dashboard

- **Tasks:** produce `RELEASE-NOTES-v2.0.0-rc.md` and the eval +
  trace dashboard for the RC build.
- **Acceptance:** dashboard shows green safety invariants and eval
  pass rate; release notes link to the contract snapshot.

---

## v2.1 Team Server Foundation

**Why now:** v2.0 RC ships a local-first single-operator agent.
A genuine enterprise platform needs a service boundary, durable
persistence, authenticated identity, and concurrency-safe approval
flow. v2.1 introduces those without changing any workflow behavior
already implemented in v1.7/v1.8 and without adding a UI.

**Dependencies:** v2.0.

**Completion demo:** the same `pr_review` and `remediation` fixtures
run end-to-end against a FastAPI server backed by PostgreSQL with a
durable worker; the CLI keeps working through a thin client mode;
approvals survive worker restart; tenant boundary is enforced at the
service layer; OpenAPI-typed REST contracts are frozen.

**Blocks if missing:** v2.2 (no place to handle webhooks), v2.3
(no API for the operator console), v2.4 (no place to host the
persistent index), v2.5 (nothing to harden).

**Non-goals:** UI, webhook handlers, live GitHub writes, pgvector,
real Jira API, OpenTelemetry export.

### v2.1.1 Service Contracts and Configuration

- **Goal:** declare the v2.1 API and persistence contracts before
  any implementation lands; pick a single, justified storage and
  worker stack and freeze it in the decision log.
- **Scope:** OpenAPI surface, settings module, deployment configs,
  and the storage / worker decisions referenced from
  `decision-log.md` and `platform-architecture-v2.md`.
- **Tasks:** see backlog tasks `v2.1.1-T1`–`v2.1.1-T3`.
- **Directories/modules:** `src/safecode/enterprise/api/contracts/`
  (planned), `src/safecode/enterprise/api/settings.py` (planned),
  `enterprise-docs/platform-architecture-v2.md`.
- **Acceptance:**
  - OpenAPI surface fully specifies runs, approvals, evidence,
    eval, traces, and health endpoints as `planned` contracts.
  - Settings module captures DSN, auth issuer, runtime mode, and
    worker mode without consuming live config in tests.
  - Storage and worker choices recorded in `decision-log.md` with
    rejected alternatives.
- **Risks:** API drift between server and CLI. Mitigation: API
  contracts and CLI/JSON contracts are pinned by snapshot tests in
  v2.1.7.
- **Non-goals:** any FastAPI route handler implementation.

### v2.1.2 Persistence Protocols and Local Backend

- **Goal:** factor an explicit repository protocol layer so file-
  backed state and database-backed state share one contract; keep
  the local filesystem backend as the default for CLI and tests.
- **Scope:** repository protocols for runs, checkpoints, approvals,
  grants, audit, evidence, eval, plus the existing
  `.sac/enterprise/` adapter that implements them.
- **Tasks:** see backlog tasks `v2.1.2-T1`–`v2.1.2-T3`.
- **Directories/modules:** `src/safecode/enterprise/persistence/`
  (planned).
- **Acceptance:**
  - Every existing workflow / approval / evidence write path goes
    through a protocol method.
  - Local file backend round-trips every entity unchanged from
    v2.0 behavior.
  - No production module references file paths directly outside
    the local backend.
- **Risks:** silent contract leak when refactoring storage.
  Mitigation: snapshot tests on entity shapes; no schema change
  vs v2.0.
- **Non-goals:** the PostgreSQL backend (`v2.1.3`).

### v2.1.3 PostgreSQL Schema and Adapter

- **Goal:** introduce a PostgreSQL backend behind the v2.1.2
  protocol, with deterministic schema migrations and a test harness
  that does not require a live database in unit tests.
- **Scope:** PostgreSQL schema, migrations, repository adapter, and
  the in-memory fake used by deterministic tests.
- **Tasks:** see backlog tasks `v2.1.3-T1`–`v2.1.3-T4`.
- **Directories/modules:** `src/safecode/enterprise/persistence/
  postgres/` (planned), `tests/enterprise/persistence/` (planned).
- **Acceptance:**
  - Schema versioned; migrations idempotent.
  - Adapter passes the same protocol contract tests as the local
    backend.
  - Tenant id is enforced as a non-null column on every owned
    table.
  - Default `psycopg` driver vendored only via existing dependency
    surface; no new top-level dependency without backlog approval.
- **Risks:** transactional boundaries differ from filesystem;
  approval consumption and audit chain must remain atomic.
  Mitigation: explicit `SERIALIZABLE` for the approval-consume
  path; protocol contract tests enforce single-use semantics.
- **Non-goals:** any service code; pgvector (`v2.4`).

### v2.1.4 FastAPI Read API

- **Goal:** expose read-only enterprise endpoints so the CLI, the
  v2.3 console, and integration tests can list runs, approvals,
  traces, evidence bundles, and eval baselines.
- **Scope:** the read surface only; no command endpoints, no
  writes that mutate workflow state.
- **Tasks:** see backlog tasks `v2.1.4-T1`–`v2.1.4-T2`.
- **Directories/modules:** `src/safecode/enterprise/api/` (planned).
- **Acceptance:**
  - All read endpoints reject unauthenticated requests.
  - Tenant scoping enforced at handler level; no cross-tenant read.
  - Health and readiness endpoints return deterministic JSON.
- **Risks:** read endpoints leaking redacted-only fields.
  Mitigation: handlers consume the same redaction profile as
  trace export.
- **Non-goals:** command endpoints (`v2.1.5`).

### v2.1.5 FastAPI Command API and Worker Lease

- **Goal:** start, resume, and approve runs through the API, with
  durable worker leasing that guarantees one writer per run.
- **Scope:** workflow run command endpoints, approval submission
  endpoints, idempotency keys, and the lease/heartbeat protocol.
- **Tasks:** see backlog tasks `v2.1.5-T1`–`v2.1.5-T4`.
- **Directories/modules:** `src/safecode/enterprise/api/`,
  `src/safecode/enterprise/worker/` (planned).
- **Acceptance:**
  - Submitting the same run twice with the same idempotency key
    yields one execution.
  - Worker crash releases the lease within a bounded interval;
    another worker resumes from the last checkpoint.
  - Approval submission and consumption emit the same audit events
    as the CLI flow.
- **Risks:** lost-update races on approval store. Mitigation:
  v2.1.3 transactional boundary plus the existing single-use
  semantics; tests cover the race directly.
- **Non-goals:** webhook ingestion (`v2.2`).

### v2.1.6 Authenticated Subject Boundary

- **Goal:** stop trusting the `--actor` flag once the API is
  reachable; resolve `RBACSubject` from an authenticated principal
  for any service-mode request.
- **Scope:** OIDC discovery + JWT validation, subject mapping into
  the existing RBAC model, optional bearer authentication for the
  CLI in server mode.
- **Tasks:** see backlog tasks `v2.1.6-T1`–`v2.1.6-T2`.
- **Directories/modules:** `src/safecode/enterprise/auth/`
  (planned).
- **Acceptance:**
  - Service-mode requests without a valid token fail closed.
  - Subject identifiers always include `tenant_id`.
  - Local CLI mode still works without auth and is the documented
    fallback.
- **Risks:** offline CLI breakage if auth is forced. Mitigation:
  explicit `runtime_mode` setting; `local` mode skips auth.
- **Non-goals:** identity provider provisioning; SSO at the org
  level (`v2.5`).

### v2.1.7 Contracts, Deployment, and Closeout

- **Goal:** freeze the v2.1 public contracts, document deployment
  and rollback, ship the demo, and update the project context for
  post-RC navigation.
- **Scope:** API snapshot tests, migration runbook, deployment
  README updates, and the v2.1 demo bundle.
- **Tasks:** see backlog tasks `v2.1.7-T1`–`v2.1.7-T3`.
- **Acceptance:**
  - API snapshot tests pass for the v2.1 surface; intentional
    changes update the snapshot in the same PR.
  - Migration runbook describes upgrade and rollback for a Team
    Server installation.
  - Demo bundle proves a clean end-to-end PR review run on the
    server profile.
- **Risks:** CLI/API divergence post-v2.1. Mitigation: same JSON
  schema serves both surfaces; CLI is a thin client when running
  in `server` mode.
- **Non-goals:** UI (`v2.3`).

---

## v2.2 Real GitHub Secure Change Workflow

**Why now:** v2.1 provides a durable service surface. v2.2 turns
fixture-driven `pr_review` and `remediation` into a real,
governed workflow with live GitHub authentication, webhook
ingestion, governed write actions, and sandboxed CI / scanner
execution.

**Dependencies:** v2.1.

**Completion demo:** a GitHub App installs into a sample
repository; a PR triggers a webhook; the workflow runs end-to-end
through the v2.1 API, posts a draft comment behind approval, and
optionally pushes a remediation branch and opens a PR; CI re-runs
Semgrep, pip-audit, and pytest in the existing sandbox; results
post back through the API.

**Blocks if missing:** every "real" demo; v2.3 (the UI has no
live runs to display); v2.4 (live Jira is the same identity
boundary).

**Non-goals:** GitLab/Bitbucket, GitHub Enterprise Cloud SLO,
incident workflows.

### v2.2.1 GitHub App Identity and Webhook Ingest

- **Goal:** authenticate as a GitHub App, validate webhook
  signatures, and persist the triggering event behind the v2.1
  API.
- **Scope:** App credential boundary (private key not in repo),
  signed-webhook handler, idempotent event store.
- **Acceptance:**
  - Webhook signature verification fails closed when the secret
    is missing or wrong.
  - The same delivery id is never processed twice.
  - Tokens never appear in logs or trace events.

### v2.2.2 Real PR Read and Sandboxed Repository Fetch

- **Goal:** replace fixture-mode `PullRequestEvidence` with a
  live GitHub read path that the v1.7/v1.8 workflows can already
  consume.
- **Scope:** evidence model unchanged; new adapter; sandboxed
  shallow checkout for the fetched ref.
- **Acceptance:**
  - Identical PR fixture and live response produce equivalent
    evidence objects.
  - Out-of-tenant repository access fails closed.

### v2.2.3 Governed PR Comment, Branch Push, and PR Open

- **Goal:** wire the governed write surface (comment / branch /
  PR open) through the approval engine, the audit log, and the
  v2.1 API.
- **Scope:** write actions remain `GATE` or `BLOCK` per the
  governance matrix; protected branches stay `BLOCK`.
- **Acceptance:**
  - No write occurs without a single-use grant bound to the
    current policy snapshot.
  - Protected-branch push attempts always fail closed.
  - Audit chain includes the GitHub api response identifier.

### v2.2.4 CI / Scanner Sandbox Execution and Callback

- **Goal:** run Semgrep, pip-audit, and pytest under the existing
  sandbox lifecycle, then post their structured results back into
  the workflow without trusting CI string output as instructions.
- **Scope:** CI runner adapter, structured result schema, callback
  endpoint.
- **Acceptance:**
  - CI output validated against a typed schema before influencing
    workflow decisions.
  - Sandbox proposal required for every command execution.

### v2.2.5 End-to-End PR Review and Remediation Flagship

- **Goal:** make a clean end-to-end PR security review and a
  remediation PR demonstrable against a real fork; ship the demo
  bundle and the network-denied deterministic integration tests.
- **Scope:** integration suites, demo recordings, runbook.
- **Acceptance:**
  - Default test lane works fully offline.
  - Live lane is opt-in and never blocks merges.

---

## v2.3 Operator Console

**Why now:** with the API and live workflows in place, an
operator who is not the engineer running the CLI needs a view of
runs, approvals, citations, patches, validation, costs, and
evals. Building it earlier would have produced a UI of mock data.

**Dependencies:** v2.1 (API), v2.2 (real runs to display).

**Completion demo:** an OIDC user logs in, sees their tenant's
runs, opens a run timeline with citations and tool calls,
approves a pending action, and downloads the evidence bundle.

**Non-goals:** policy editing UI, workflow authoring UI, billing.

### v2.3.1 Console Shell and Authentication

- **Goal:** boot a React/Next.js application against the v2.1
  API with OIDC login and tenant-aware navigation.
- **Acceptance:** unauthenticated users cannot reach data routes;
  cross-tenant URLs fail closed.

### v2.3.2 Run List, Timeline, and Trace Viewer

- **Goal:** browse runs and inspect a single run timeline and
  trace with the same redaction profiles used by the CLI.
- **Acceptance:** sensitive fields hidden by default; "debug"
  profile gated by policy bit.

### v2.3.3 Approval Inbox and Patch Review

- **Goal:** review pending approvals, inspect proposed patches and
  comments, and approve / reject through the API.
- **Acceptance:** model-driven actions cannot bypass the
  approval verb; UI submits the same single-use grant the CLI
  produces.

### v2.3.4 Evidence, Eval, and Cost Views

- **Goal:** surface evidence bundles, eval dashboard data, and
  cost budgets so operators can answer "did the agent stay in
  budget and produce auditable artifacts".
- **Acceptance:** read-only; no UI surface for ratchet bypass.

### v2.3.5 Operator Console Acceptance and Demo

- **Goal:** ship the demo and pin the UI / API contract.
- **Acceptance:** demo bundle works against the v2.2 deployment
  profile; contract snapshot covers the UI/API boundary.

---

## v2.4 Enterprise Knowledge, Tickets, and Memory

**Why now:** until v2.3, retrieval uses the v1.1 in-process
embedding store. To support real enterprises with large
knowledge bases, incremental ingestion, and access-controlled
sources, we need persistent hybrid retrieval, a real Jira
connector, and governed long-term memory. We also need the
secure-planning workflow that consumes them.

**Dependencies:** v2.1 (persistence and identity), v2.2 (real
GitHub identity model).

**Completion demo:** policy documents and code are ingested
incrementally into PostgreSQL+pgvector; a Jira ticket triggers a
`secure_planning` workflow that retrieves cited evidence,
proposes a plan, asks for approval, and records the plan with
provenance and expiry. Long-term memory facts are admitted,
revoked, and audited.

**Non-goals:** crawler scheduling outside the connectors,
LLM-based reranking that requires live providers.

### v2.4.1 Persistent Hybrid Retrieval (PostgreSQL+pgvector)

- **Goal:** move the v1.1 in-process semantic store onto a
  pgvector-backed persistent index without changing the public
  retrieval contract.
- **Acceptance:** existing retrieval eval suites pass; tenant
  filter enforced in SQL, not in application code only.

### v2.4.2 Incremental Ingest, Freshness, and ACL Sync

- **Goal:** ingest only the changed slice of a source on each
  refresh, with deterministic chunk-id stability and ACL/tenant
  sync.
- **Acceptance:** re-ingesting an unchanged source is a no-op;
  ACL changes propagate before the next retrieval round.

### v2.4.3 Reranker and Query Rewriting

- **Goal:** add a deterministic reranker and a small query
  rewriting layer that improve retrieval precision without
  depending on a live LLM.
- **Acceptance:** reranker uses the same mock embeddings in
  tests; ratchet enforced.

### v2.4.4 Real Jira Connector

- **Goal:** replace the fixture-mode Jira loader with a live
  connector using the v2.1 auth boundary and the existing
  approval gate.
- **Acceptance:** read uses tenant-scoped credentials; write
  remains GATE; offline fallback preserved.

### v2.4.5 Secure-Planning Workflow

- **Goal:** wire the `secure_planning` task end-to-end through
  retrieval, reasoning, approval, and audit.
- **Acceptance:** planning artifact contains citations,
  alternatives, and a revisit trigger; no proposal-only
  shortcuts.

### v2.4.6 Governed Long-Term Memory

- **Goal:** admit, revoke, and expire memory facts under the
  same approval engine and audit chain; never inject untrusted
  text into the model.
- **Acceptance:** every fact has provenance, approver, expiry,
  and revocation trail.

---

## v2.5 Production Hardening

**Why now:** v2.1 through v2.4 add features; v2.5 closes the
operability gap before GA.

**Dependencies:** v2.2, v2.3, v2.4.

**Completion demo:** OpenTelemetry traces exported to a local
collector; deliberate worker kill is recovered; a deliberately
bad payload lands in the dead-letter queue; load test holds
the latency budget; backup and restore round-trip; on-prem
deploy automation reproduces the same stack.

**Non-goals:** chaos engineering, geo-redundancy, multi-region
HA.

### v2.5.1 OpenTelemetry Export

- **Goal:** add a parallel OTel exporter behind the existing
  trace emitter; redaction policy unchanged.
- **Acceptance:** exporter can be disabled by config without
  losing local trace files.

### v2.5.2 Worker Recovery and Dead-Letter Behavior

- **Goal:** make the worker resilient to crashes, deadlocks,
  and poison messages.
- **Acceptance:** poisoned message reaches the DLQ; healthy
  workers continue.

### v2.5.3 Concurrency, Locking, Rate Limits, and Cost Budgets

- **Goal:** make the API safe under load.
- **Acceptance:** documented limits; tests cover boundary
  conditions; cost budget enforced against `RunCosts`.

### v2.5.4 Backup, Restore, and Schema Migrations

- **Goal:** every persistence layer (Postgres tables, pgvector,
  filesystem evidence) has a documented and tested backup /
  restore path and a forward migration strategy.
- **Acceptance:** a v2.1.3 schema upgrade is reversible; restore
  verifies audit chain and evidence hashes.

### v2.5.5 Load and Threat Model

- **Goal:** establish a stable load and threat model and use it
  in CI ratchet.
- **Acceptance:** ratchet on key endpoints; threat model
  captures the v2.0 RC findings and the v2.1+ new boundaries.

### v2.5.6 On-Prem Deploy Automation and Upgrade/Rollback

- **Goal:** make on-prem installation reproducible.
- **Acceptance:** a single command brings up the stack; an
  upgrade and rollback are tested.

---

## v3.0 Enterprise GA

**Why last:** GA is a sign-off, not a feature dump.

**Dependencies:** v2.5.

**Completion demo:** a customer-facing GA build with supported
contracts, the v2.0 RC contract still honored where compatible,
a signed external security review, production deployment
evidence, the flagship workflows, and release notes.

### v3.0.1 GA Contract and Migration Compatibility

- **Goal:** publish the supported public contracts and the
  upgrade path from v2.0 RC.
- **Acceptance:** contract changes have migration tests.

### v3.0.2 Signed Security Review

- **Goal:** a real (third-party or formally-tracked internal)
  security review with no open high/critical findings.
- **Acceptance:** review filed; findings tracked or accepted.

### v3.0.3 Production Deployment Evidence

- **Goal:** at least one production-like deployment with
  observed metrics, audit chain, and incident handling.
- **Acceptance:** evidence captured under the deployment-profile
  rules; no debug artifacts.

### v3.0.4 Flagship Demos and GA Release Notes

- **Goal:** demo bundles for PR review, remediation, secure
  planning, evidence export, and operator workflows; release
  notes that are accurate at GA.
- **Acceptance:** demos repeat the v2.2 acceptance against GA
  contracts; release notes link the v2.0 → v3.0 migration.

---

## Cross-Stage Invariants

These hold for every sub-plan and override anything that contradicts
them.

1. The mock LLM provider is the default for tests. No sub-plan
   requires live LLM credentials to pass CI.
2. No sub-plan adds a hard dependency on a hosted service before
   v2.0. Optional dependencies are gated by feature extras.
3. Every write path keeps the existing SafeCodeAgent invariants:
   policy gate, checkpoint, approval, audit, redaction, rollback.
4. Project-local configuration cannot weaken org/user policy.
5. Tool classification is local code, not server data.
6. Retrieved content is data, not instructions.
7. Every sub-plan ships its own tests; no merged PR can lower test
   coverage on enterprise modules below the previous PR.
8. Public CLI surface remains compatible across patches within a
   stage version. Breaking changes require a new stage version.
9. Post-v2.0 stages may add a service surface but must not remove
   the local-first CLI path; the CLI either runs in `local` mode
   (file backend) or in `server` mode (thin client over the v2.1
   API).
10. v2.1+ stages compose the v2.0 safety kernel and the
    `safecode.enterprise` modules; no v2.0 contract is silently
    weakened to make a v2.1+ feature easier to implement. Any
    change to a frozen contract requires a new decision log entry
    and a snapshot update in the same PR.
