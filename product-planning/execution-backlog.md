# Execution Backlog

**Implementation status (v2.0 RC):** Stages v1.0–v2.0 are delivered. Post-RC
stages v2.1–v3.0 are planned; v2.1 is detailed at PR-level, v2.2 at PR-level,
and v2.3–v3.0 remain mid-grain pending its predecessor. See
`.agents/context/progress.json` for live stage state.
This file is the line-by-line backlog the implementation team (Claude
Code, Codex, or human contributors) will draw from to execute
`version-roadmap.md`. Tasks here are sized for a single small PR each.

Conventions:

- **ID** uses `<version>-T<n>`. Example: `v1.1.1-T1`. Stable across
  the life of the backlog.
- **Files/Modules** refers to *new or modified* paths. Paths must be
  the ones actually created by the task, not generic prefixes.
- **Tests** lists pytest paths that will exist after the PR merges.
- **Acceptance** is a concrete, checkable list.
- **Estimate** is in PR-days (a PR-day is one focused day of one
  engineer). Half-day granularity allowed.
- **Risk** lists named risks with a brief mitigation.
- **Dependencies** lists prerequisite task IDs; a task may not start
  until its dependencies are merged.

Stages v1.1–v1.4 have full per-task detail. Stages v1.5–v2.0 list
mid-grain tasks; each will be expanded to the same level before
implementation.

> A task is *done* only when every line in **Acceptance** is true.
> "I implemented it" without acceptance check is not done.

---

## v1.0 Enterprise Branch Reset and Planning

### v1.0.1-T1 — Write planning documents
- **Version:** v1.0.1
- **Title:** Land the thirteen planning Markdown files
- **Description:** Create or overwrite the planning files listed in
  the parent task (this PR is that work).
- **Dependencies:** none.
- **Files/Modules:**
  - `product-planning/version-roadmap.md`
  - `product-planning/milestone-acceptance.md`
  - `product-planning/execution-backlog.md`
  - `product-planning/interview-master-narrative.md`
  - `product-planning/decision-log.md`
  - `product-planning/claude-code-execution-guide.md`
  - `enterprise-docs/system-architecture-v1.md`
  - `enterprise-docs/data-models.md`
  - `enterprise-docs/workflow-design.md`
  - `enterprise-docs/rag-implementation-plan.md`
  - `enterprise-docs/security-governance-plan.md`
  - `enterprise-docs/evaluation-plan.md`
  - `enterprise-docs/agentops-observability-plan.md`
- **Tests:** none in this PR.
- **Acceptance:**
  - All thirteen files exist with non-empty H1 titles.
  - Every file is linked from either
    `product-planning/README.md` (later in v1.0.3) or
    `enterprise-docs/README.md` (later in v1.0.3).
  - No file restores legacy `docs/` content.
- **Estimate:** 1.0 PR-day.
- **Risk:** scope creep into prose with no engineering hook. Mitigation:
  every plan file must name a file path, module, test, or CLI command.

### v1.0.2-T1 — Reserve enterprise namespace
- **Version:** v1.0.2
- **Title:** Create `safecode.enterprise` namespace skeleton
- **Description:** Add empty package and version stub.
- **Dependencies:** v1.0.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/__init__.py` (empty)
  - `src/safecode/enterprise/__about__.py` (`__version__ = "0.0.0-dev"`)
  - `tests/enterprise/__init__.py` (empty)
  - `tests/enterprise/conftest.py` (empty)
- **Tests:**
  - `tests/enterprise/test_namespace_import.py`
- **Acceptance:**
  - Import test passes.
  - `pyproject.toml` unchanged (no new dependency).
  - Full `pytest -q` still green.
- **Estimate:** 0.25 PR-day.
- **Risk:** accidental public symbols. Mitigation: keep `__init__.py`
  empty.

### v1.0.3-T1 — Cross-link planning docs
- **Version:** v1.0.3
- **Title:** Update READMEs to reference new planning files
- **Dependencies:** v1.0.1-T1.
- **Files/Modules:**
  - `product-planning/README.md`
  - `enterprise-docs/README.md`
- **Tests:** none (link presence covered in v1.0.4-T1).
- **Acceptance:**
  - Every new file is linked from one of the two READMEs.
- **Estimate:** 0.25 PR-day.
- **Risk:** drift. Mitigation: v1.0.4-T1 test.

### v1.0.4-T1 — Planning presence test
- **Version:** v1.0.4
- **Title:** Add `tests/enterprise/test_planning_present.py`
- **Dependencies:** v1.0.1-T1, v1.0.2-T1, v1.0.3-T1.
- **Files/Modules:**
  - `tests/enterprise/test_planning_present.py`
- **Tests:** itself.
- **Acceptance:**
  - Test exists, parametrized over the thirteen filenames.
  - Removing any file or H1 fails the test.
- **Estimate:** 0.25 PR-day.

---

## v1.1 RAG Security Knowledge Base MVP

### v1.1.1-T1 — KnowledgeSource and SourceType
- **Version:** v1.1.1
- **Title:** Define `KnowledgeSource` Pydantic model and `SourceType` enum
- **Dependencies:** v1.0.2-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/__init__.py`
  - `src/safecode/enterprise/rag/source_registry.py`
- **Tests:**
  - `tests/enterprise/rag/test_source_registry_models.py`
- **Acceptance:**
  - `KnowledgeSource` has fields: `source_id`, `source_type`, `name`,
    `path_or_uri`, `owner`, `permission_scope` (list[str]),
    `refresh_cadence`, `parser`, `metadata` (dict).
  - `SourceType` enum has at least: `security_policy`,
    `secure_coding_standard`, `architecture_doc`, `code`,
    `historical_fix`, `scanner_finding`, `runbook`.
  - Round-trip JSON serialization preserves field order.
- **Estimate:** 0.5 PR-day.
- **Risk:** field set drift. Mitigation: pin a snapshot test.

### v1.1.1-T2 — SourceRegistry manifest loader
- **Title:** Load registry from YAML manifest
- **Dependencies:** v1.1.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/source_registry.py` (extend)
  - `examples/enterprise/knowledge_sources.yaml`
- **Tests:**
  - `tests/enterprise/rag/test_source_registry.py`
- **Acceptance:**
  - `SourceRegistry.from_manifest(path)` accepts the example YAML
    with four entries (policy, code, scanner, runbook).
  - Duplicate `source_id` raises `DuplicateSourceIdError`.
  - Missing required keys raise typed `ManifestValidationError` with
    the offending key in the message.
- **Estimate:** 0.5 PR-day.
- **Risk:** YAML loader ambiguity. Mitigation: use `yaml.safe_load`
  only.

### v1.1.1-T3 — Markdown loader
- **Dependencies:** v1.1.1-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/loaders/__init__.py`
  - `src/safecode/enterprise/rag/loaders/loader_markdown.py`
- **Tests:**
  - `tests/enterprise/rag/test_loader_markdown.py`
- **Acceptance:**
  - Loader emits one `RawRecord` per H1 section (or one record for the
    whole file when no H1 exists).
  - Non-empty body before the first H1 becomes a separate preamble
    record with stable `record_id`.
  - Each record carries `text`, `path`, `span`, and
    `metadata={"headings": [...]}` with H1→H6 hierarchy preserved.
  - Front-matter YAML, when present, lands in `metadata`.
  - `record_id` is stable, deterministic, and reproducible across
    runs.
- **Estimate:** 0.5 PR-day.

### v1.1.1-T4 — Code loader
- **Dependencies:** v1.1.1-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/loaders/loader_code.py`
- **Tests:**
  - `tests/enterprise/rag/test_loader_code.py`
- **Acceptance:**
  - Loader supports `.py` only in MVP.
  - Emits one `RawRecord` per top-level function or class with
    line-range metadata.
  - Files larger than 2 MB are skipped with a warning event.
- **Estimate:** 0.5 PR-day.
- **Risk:** Python AST drift. Mitigation: standard `ast` module;
  no third-party parser.

### v1.1.1-T5 — SARIF loader
- **Dependencies:** v1.1.1-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/loaders/loader_sarif.py`
- **Tests:**
  - `tests/enterprise/rag/test_loader_sarif.py`
- **Acceptance:**
  - Supports SARIF 2.1.0 only (others raise
    `UnsupportedSarifVersionError`).
  - Emits one `RawRecord` per SARIF result with location metadata.
- **Estimate:** 0.5 PR-day.

### v1.1.1-T6 — Semgrep loader
- **Dependencies:** v1.1.1-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/loaders/loader_semgrep.py`
- **Tests:**
  - `tests/enterprise/rag/test_loader_semgrep.py`
- **Acceptance:**
  - Accepts Semgrep JSON `results` array shape.
  - Stable `record_id` per finding (deterministic across runs).
- **Estimate:** 0.5 PR-day.

### v1.1.2-T1 — Chunk and Citation models
- **Dependencies:** v1.1.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/models.py`
- **Tests:**
  - `tests/enterprise/rag/test_chunk_model.py`
  - `tests/enterprise/rag/test_citation_model.py`
- **Acceptance:**
  - `Chunk` has fields: `chunk_id`, `source_id`, `path`,
    `start_line`, `end_line`, `source_type`, `permission_scope`,
    `freshness`, `text`, `hash`, `metadata`.
  - `Citation` has fields: `source_id`, `source_type`, `path`,
    `start_line`, `end_line`, `score`, `selection_reason`,
    `permission_verdict`, `freshness`, `hash`.
  - JSON round-trip preserves all fields.
- **Estimate:** 0.5 PR-day.

### v1.1.2-T2 — Enterprise chunker wrapper
- **Dependencies:** v1.1.2-T1, v1.1.1-T3, v1.1.1-T4.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/chunker.py`
- **Tests:**
  - `tests/enterprise/rag/test_chunker.py`
  - `tests/enterprise/rag/test_chunk_id_stability.py`
- **Acceptance:**
  - Markdown and Python inputs both produce `Chunk` records.
  - Same input file produces identical chunk ids across two runs.
  - Legacy `src/safecode/index/chunker.py` is not modified.
- **Estimate:** 0.5 PR-day.
- **Risk:** legacy chunker behavior differs by file type. Mitigation:
  add a thin adapter; do not duplicate logic.

### v1.1.2-T3 — Permission scope assignment
- **Dependencies:** v1.1.2-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/permission_scope.py`
- **Tests:**
  - `tests/enterprise/rag/test_permission_scope.py`
- **Acceptance:**
  - Each `Chunk.permission_scope` is set from the parent
    `KnowledgeSource.permission_scope`.
  - Chunks without a scope are dropped with a `chunk.unscoped`
    event.
- **Estimate:** 0.25 PR-day.

### v1.1.3-T1 — Lexical scorer
- **Dependencies:** v1.1.2-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/lexical.py`
- **Tests:**
  - `tests/enterprise/rag/test_lexical_scorer.py`
- **Acceptance:**
  - BM25-ish scoring over chunk text; no third-party dependency.
  - Idempotent on identical queries.
- **Estimate:** 0.5 PR-day.
- **Risk:** scorer simplicity hurts retrieval quality. Mitigation:
  documented in `decision-log.md`; revisit at v1.6 if needed.

### v1.1.3-T2 — Semantic scorer
- **Dependencies:** v1.1.2-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/semantic.py`
- **Tests:**
  - `tests/enterprise/rag/test_semantic_scorer.py`
- **Acceptance:**
  - Wraps the existing `src/safecode/index/embedding_backend.py`.
  - Uses the mock embedding backend in unit tests for determinism.
  - Returns chunk-id-keyed scores.
- **Estimate:** 0.5 PR-day.

### v1.1.3-T3 — HybridRetriever
- **Dependencies:** v1.1.3-T1, v1.1.3-T2, v1.1.2-T3.
- **Files/Modules:**
  - `src/safecode/enterprise/rag/retriever.py`
- **Tests:**
  - `tests/enterprise/rag/test_hybrid_retriever.py`
  - `tests/enterprise/rag/test_permission_filter.py`
- **Acceptance:**
  - `HybridRetriever.retrieve(query, k, actor_scope, filters)`
    returns at most `k` citations sorted by combined score.
  - Permission filter drops chunks not in `actor_scope`.
  - Combined score = `0.5 * lexical + 0.5 * semantic` (configurable).
- **Estimate:** 1.0 PR-day.

### v1.1.3-T4 — `sac enterprise retrieve` CLI
- **Dependencies:** v1.1.3-T3.
- **Files/Modules:**
  - `src/safecode/cli_enterprise.py` (new module)
- **Tests:**
  - `tests/enterprise/cli/test_cli_retrieve.py`
- **Acceptance:**
  - `sac enterprise retrieve "<query>" --manifest <path>` prints
    a JSON array of citations.
  - Cap at `RAG_MAX_CITATIONS` (default 8).
  - Exit code 0 when ≥1 citation; 2 when none.
- **Estimate:** 0.5 PR-day.

### v1.1.4-T1 — Retrieval eval cases
- **Dependencies:** v1.1.3-T3.
- **Files/Modules:**
  - `tests/enterprise/eval/cases/retrieval/sql_injection.yaml`
  - `tests/enterprise/eval/cases/retrieval/path_traversal.yaml`
  - `tests/enterprise/eval/cases/retrieval/stale_doc.yaml`
- **Tests:** loaded by v1.1.4-T2.
- **Acceptance:**
  - Each case lists `query`, `actor_scope`, `expected_source_ids`,
    and `forbidden_source_ids`.
- **Estimate:** 0.5 PR-day.

### v1.1.4-T2 — Retrieval eval runner
- **Dependencies:** v1.1.4-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/eval/retrieval.py`
  - `tests/enterprise/eval/test_retrieval_quality.py`
- **Acceptance:**
  - Runner computes recall@k, MRR, and grounding rate per case.
  - Test compares with baseline file
    `tests/enterprise/eval/baselines/retrieval_v1_1.json`.
- **Estimate:** 0.5 PR-day.

### v1.1.4-T3 — Retrieval baseline
- **Dependencies:** v1.1.4-T2.
- **Files/Modules:**
  - `tests/enterprise/eval/baselines/retrieval_v1_1.json`
- **Acceptance:**
  - Baseline checked in with date and commit fields.
  - Updating baseline requires `--update-baseline` flag.
- **Estimate:** 0.25 PR-day.

---

## v1.2 LangGraph Security Workflow MVP

### v1.2.1-T1 — Enum and risk-tier types
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/types.py`
- **Tests:**
  - `tests/enterprise/workflow/test_types.py`
- **Acceptance:**
  - `TaskType` enum: `pr_review`, `remediation`, `secure_planning`,
    `compliance_export`.
  - `RiskTier` enum: `low`, `medium`, `high`, `critical`.
  - `WorkflowStatus` enum: `pending`, `running`, `awaiting_approval`,
    `succeeded`, `failed`, `rejected`, `blocked`.
- **Estimate:** 0.25 PR-day.

### v1.2.1-T2 — EnterpriseRunState model
- **Dependencies:** v1.2.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/state.py`
- **Tests:**
  - `tests/enterprise/workflow/test_state_round_trip.py`
- **Acceptance:**
  - All fields from `enterprise-docs/data-models.md` present.
  - JSON round-trip lossless.
  - `model_dump_json()` is stable across runs (sorted keys).
- **Estimate:** 0.5 PR-day.

### v1.2.1-T3 — Node contracts
- **Dependencies:** v1.2.1-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/nodes/__init__.py`
  - One file per node: `classify.py`, `collect_context.py`,
    `retrieve.py`, `analyze.py`, `plan.py`, `propose.py`,
    `validate.py`, `approval.py`, `finalize.py`.
- **Tests:**
  - `tests/enterprise/workflow/test_node_contracts.py`
- **Acceptance:**
  - Each node exports `run(state) -> NodePatch` with typed return.
  - Returned `NodePatch` includes `events` list (typed
    `TraceEventDraft`).
- **Estimate:** 0.75 PR-day.

### v1.2.2-T1 — LocalOrchestrator
- **Dependencies:** v1.2.1-T3.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/orchestrator.py`
- **Tests:**
  - `tests/enterprise/workflow/test_orchestrator_happy_path.py`
- **Acceptance:**
  - Orchestrator runs nodes in declared order, applies patches,
    persists checkpoints.
  - Unknown task type raises `UnknownTaskTypeError`.
- **Estimate:** 0.75 PR-day.

### v1.2.2-T2 — Checkpoint persistence
- **Dependencies:** v1.2.2-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/checkpoint.py`
- **Tests:**
  - `tests/enterprise/workflow/test_orchestrator_resume.py`
- **Acceptance:**
  - State written to `.sac/enterprise/runs/<run_id>/state.json`
    after each node.
  - Resume skips completed nodes.
- **Estimate:** 0.5 PR-day.

### v1.2.2-T3 — `sac enterprise workflow run/resume/gc` CLI
- **Dependencies:** v1.2.2-T2.
- **Files/Modules:**
  - `src/safecode/cli_enterprise.py` (extend)
- **Tests:**
  - `tests/enterprise/cli/test_cli_workflow_run.py`
- **Acceptance:**
  - `run --task pr_review --input <path>` returns a `run_id`.
  - `resume <run_id>` continues an interrupted run.
  - `gc --older-than 7d` removes stale run directories.
- **Estimate:** 0.5 PR-day.

### v1.2.3-T1 — LangGraph dependency under extra
- **Dependencies:** v1.2.2-T3.
- **Files/Modules:**
  - `pyproject.toml` (add `[project.optional-dependencies]
    enterprise = ["langgraph>=X.Y,<X.Z"]`)
- **Tests:**
  - `tests/enterprise/workflow/test_optional_extra_import.py`
- **Acceptance:**
  - Default install does not pull `langgraph`.
  - `uv sync --extra enterprise` installs `langgraph`.
- **Estimate:** 0.25 PR-day.
- **Risk:** pyproject conflicts with existing extras. Mitigation:
  read current pyproject and add only the extras section if missing.

### v1.2.3-T2 — StateGraph adapter
- **Dependencies:** v1.2.3-T1, v1.2.2-T3.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/graph.py`
- **Tests:**
  - `tests/enterprise/workflow/test_graph_topology.py`
  - `tests/enterprise/workflow/test_graph_conditional_edges.py`
- **Acceptance:**
  - Topology test enumerates expected nodes and edges.
  - Conditional edges include: missing_evidence → retrieve,
    high_risk → approval, validation_failed → repair_or_blocker.
- **Estimate:** 0.75 PR-day.

### v1.2.3-T3 — Runtime flag
- **Dependencies:** v1.2.3-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/orchestrator.py` (extend)
- **Tests:**
  - Re-run existing workflow tests with `WORKFLOW_RUNTIME=langgraph`
    in CI matrix.
- **Acceptance:**
  - Default runtime remains `local` for unit tests.
  - Setting env to `langgraph` produces equivalent outputs on the
    happy path.
- **Estimate:** 0.5 PR-day.

### v1.2.4-T1 — Approval request store
- **Dependencies:** v1.2.2-T3.
- **Files/Modules:**
  - `src/safecode/enterprise/approvals/__init__.py`
  - `src/safecode/enterprise/approvals/store.py`
- **Tests:**
  - `tests/enterprise/approvals/test_request_store.py`
- **Acceptance:**
  - Requests persisted under
    `.sac/enterprise/runs/<run_id>/approvals/<request_id>.json`.
  - Duplicate write raises `ApprovalRequestExistsError`.
- **Estimate:** 0.5 PR-day.

### v1.2.4-T2 — Interrupt primitive
- **Dependencies:** v1.2.4-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/interrupt.py`
- **Tests:**
  - `tests/enterprise/workflow/test_approval_interrupt.py`
- **Acceptance:**
  - `pause_for_approval(state, request)` writes the request and
    raises `WorkflowInterrupted`.
  - Orchestrator persists state before re-raising.
- **Estimate:** 0.5 PR-day.

### v1.2.4-T3 — Approval CLI (basic)
- **Dependencies:** v1.2.4-T1.
- **Files/Modules:**
  - `src/safecode/cli_enterprise.py` (extend)
- **Tests:**
  - `tests/enterprise/cli/test_cli_approval_flow.py`
- **Acceptance:**
  - `sac enterprise approval list/show/approve/reject` operate on
    the request store.
  - Approving consumes the request; second approval raises
    `RequestAlreadyConsumedError`.
- **Estimate:** 0.5 PR-day.

---

## v1.3 Tool/MCP Enterprise Connector Layer

### v1.3.1-T1 — ToolSpec and ToolRegistry
- **Files/Modules:**
  - `src/safecode/enterprise/tools/__init__.py`
  - `src/safecode/enterprise/tools/registry.py`
- **Tests:**
  - `tests/enterprise/tools/test_registry_round_trip.py`
- **Acceptance:**
  - `ToolSpec` fields per `enterprise-docs/data-models.md`.
  - Unknown tool returns `None`.
  - Unregistered tool requested for execution raises
    `ToolNotRegisteredError`.
- **Estimate:** 0.5 PR-day.

### v1.3.1-T2 — Native tool spec wrappers
- **Dependencies:** v1.3.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/tools/native_specs.py`
- **Tests:**
  - `tests/enterprise/tools/test_native_tool_specs_present.py`
- **Acceptance:**
  - All six legacy native tools present: `read_file`, `search`,
    `command`, `github_read`, `github_write`, `web_fetch`.
  - Approval tiers match the
    `security-governance-plan.md` action matrix.
- **Estimate:** 0.5 PR-day.

### v1.3.2-T1 — PullRequestEvidence model
- **Dependencies:** v1.3.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/connectors/models.py`
- **Tests:**
  - `tests/enterprise/connectors/test_pull_request_evidence_model.py`
- **Acceptance:**
  - Model has title, body, files, hunks, base/head refs, author,
    labels, reviewers.
- **Estimate:** 0.25 PR-day.

### v1.3.2-T2 — GitHub PR connector
- **Dependencies:** v1.3.2-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/connectors/__init__.py`
  - `src/safecode/enterprise/connectors/github_pr.py`
- **Tests:**
  - `tests/enterprise/connectors/test_github_pr_evidence.py`
  - `tests/enterprise/connectors/test_github_pr_redaction.py`
- **Acceptance:**
  - Default offline mode reads from fixture JSON.
  - Live mode reuses the legacy `github_read_tools` and the
    existing network policy gate; not exercised in unit tests.
  - Redaction drops `Authorization` and any `gh[ps]_…` tokens.
- **Estimate:** 0.75 PR-day.

### v1.3.2-T3 — Wire connector to `collect_context` node
- **Dependencies:** v1.3.2-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/nodes/collect_context.py` (extend)
- **Tests:**
  - `tests/enterprise/workflow/test_collect_context_pr.py`
- **Acceptance:**
  - When task type is `pr_review`, node attaches a
    `PullRequestEvidence` to state.
- **Estimate:** 0.25 PR-day.

### v1.3.3-T1 — IssueEvidence model
- **Files/Modules:**
  - `src/safecode/enterprise/connectors/models.py` (extend)
- **Tests:**
  - `tests/enterprise/connectors/test_issue_evidence_model.py`
- **Estimate:** 0.25 PR-day.

### v1.3.3-T2 — Issue connector
- **Dependencies:** v1.3.3-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/connectors/issue.py`
- **Tests:**
  - `tests/enterprise/connectors/test_issue_markdown.py`
  - `tests/enterprise/connectors/test_issue_jira_json.py`
- **Acceptance:**
  - Markdown and Jira-JSON sources produce identical shape.
  - Missing severity defaults to `unknown`.
- **Estimate:** 0.5 PR-day.

### v1.3.4-T1 — SecurityFinding model
- **Files/Modules:**
  - `src/safecode/enterprise/scanners/__init__.py`
  - `src/safecode/enterprise/scanners/models.py`
- **Tests:**
  - `tests/enterprise/scanners/test_finding_model.py`
- **Acceptance:**
  - Fields per `enterprise-docs/data-models.md`.
- **Estimate:** 0.25 PR-day.

### v1.3.4-T2 — Semgrep normalizer
- **Dependencies:** v1.3.4-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/scanners/semgrep.py`
- **Tests:**
  - `tests/enterprise/scanners/test_semgrep_normalize.py`
- **Acceptance:**
  - Deterministic `finding_id` from rule + path + line.
  - Unsupported schema → `UnsupportedScannerVersionError`.
- **Estimate:** 0.5 PR-day.

### v1.3.4-T3 — pip-audit normalizer
- **Dependencies:** v1.3.4-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/scanners/pip_audit.py`
- **Tests:**
  - `tests/enterprise/scanners/test_pip_audit_normalize.py`
- **Acceptance:**
  - Maps CVE id, package, severity, advisory link.
- **Estimate:** 0.5 PR-day.

### v1.3.4-T4 — Sandbox-proposal-gated scanner invocation
- **Dependencies:** v1.3.4-T2, v1.3.4-T3.
- **Files/Modules:**
  - `src/safecode/enterprise/scanners/invoke.py`
- **Tests:**
  - `tests/enterprise/scanners/test_scanner_invocation_is_proposal.py`
- **Acceptance:**
  - Calls the existing sandbox proposal pipeline; no shell strings;
    refuses to run without approval.
- **Estimate:** 0.5 PR-day.

### v1.3.5-T1 — MCP allowlist schema
- **Files/Modules:**
  - `src/safecode/enterprise/connectors/mcp_allowlist.py`
  - `examples/enterprise/mcp_allowlist.yaml`
- **Tests:**
  - `tests/enterprise/connectors/test_mcp_allowlist_schema.py`
- **Acceptance:**
  - Allowlist maps `<server_id>:<tool>` to enterprise category and
    approval tier.
  - Missing entry defaults to `BLOCK`.
- **Estimate:** 0.25 PR-day.

### v1.3.5-T2 — MCP adapter
- **Dependencies:** v1.3.5-T1, v1.3.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/connectors/mcp_adapter.py`
- **Tests:**
  - `tests/enterprise/connectors/test_mcp_registration.py`
  - `tests/enterprise/connectors/test_mcp_server_classification_ignored.py`
  - `tests/enterprise/connectors/test_mcp_output_redaction.py`
- **Acceptance:**
  - Discovery delegates to `src/safecode/mcp/discovery.py`.
  - Registry receives only tools allowed by the allowlist.
  - Server-claimed `category` is logged but not used for decisions.
  - Output capped at 4 KB after redaction.
- **Estimate:** 0.75 PR-day.

---

## v1.4 Security Governance, RBAC, Approval Engine

### v1.4.1-T1 — Policy model and resolver
- **Files/Modules:**
  - `src/safecode/enterprise/policy/__init__.py`
  - `src/safecode/enterprise/policy/models.py`
  - `src/safecode/enterprise/policy/resolver.py`
- **Tests:**
  - `tests/enterprise/policy/test_resolver_precedence.py`
- **Acceptance:**
  - Resolver loads org/user/project/env/workflow layers in order.
  - `PolicySnapshot` includes the merged map and the source of each
    key.
- **Estimate:** 0.75 PR-day.

### v1.4.1-T2 — No-weakening rule
- **Dependencies:** v1.4.1-T1.
- **Tests:**
  - `tests/enterprise/policy/test_no_weakening.py`
- **Acceptance:**
  - Project layer attempting to upgrade `github_write` from `GATE`
    to `AUTO` is rejected; snapshot keeps `GATE` and emits
    `policy.project_override_blocked`.
- **Estimate:** 0.25 PR-day.

### v1.4.2-T1 — Role enum and subject model
- **Files/Modules:**
  - `src/safecode/enterprise/rbac/__init__.py`
  - `src/safecode/enterprise/rbac/models.py`
- **Tests:**
  - `tests/enterprise/rbac/test_subject_model.py`
- **Acceptance:**
  - Roles: `viewer`, `developer`, `security_reviewer`, `maintainer`,
    `platform_admin`.
  - Subject includes `tenant_id` (defaulting to `local`).
- **Estimate:** 0.25 PR-day.

### v1.4.2-T2 — Permission map
- **Dependencies:** v1.4.2-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/rbac/permissions.py`
- **Tests:**
  - `tests/enterprise/rbac/test_role_to_permission_map.py`
- **Acceptance:**
  - Matches the matrix in `security-governance-plan.md`.
- **Estimate:** 0.5 PR-day.

### v1.4.2-T3 — `--as-role` flag (policy-gated)
- **Dependencies:** v1.4.2-T2, v1.4.1-T1.
- **Files/Modules:**
  - `src/safecode/cli_enterprise.py` (extend)
- **Tests:**
  - `tests/enterprise/rbac/test_as_role_flag_blocked.py`
- **Acceptance:**
  - Flag is rejected unless org policy `allow_as_role_flag=true`.
- **Estimate:** 0.25 PR-day.

### v1.4.3-T1 — ApprovalDecision and engine
- **Dependencies:** v1.4.1-T1, v1.4.2-T2, v1.3.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/approvals/engine.py`
- **Tests:**
  - `tests/enterprise/approvals/test_decision_matrix.py`
  - `tests/enterprise/approvals/test_decision_with_rbac.py`
- **Acceptance:**
  - Decision is the strictest of policy, RBAC, and tool spec.
  - Decision references the active `policy_snapshot_id`.
- **Estimate:** 0.75 PR-day.

### v1.4.3-T2 — Grant store and single-use enforcement
- **Dependencies:** v1.4.3-T1, v1.2.4-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/approvals/store.py` (extend)
- **Tests:**
  - `tests/enterprise/approvals/test_grant_single_use.py`
- **Acceptance:**
  - Grants persisted; consumption marks them used.
  - Second consumption raises `GrantAlreadyConsumedError`.
- **Estimate:** 0.5 PR-day.

### v1.4.4-T1 — Rich approval CLI
- **Dependencies:** v1.2.4-T3, v1.4.3-T2.
- **Files/Modules:**
  - `src/safecode/cli_enterprise.py` (extend)
  - `src/safecode/enterprise/approvals/cli_render.py`
- **Tests:**
  - `tests/enterprise/cli/test_cli_approval_render.py`
  - `tests/enterprise/cli/test_cli_approval_revoke.py`
- **Acceptance:**
  - `list --pending`, `show`, `approve [--note]`,
    `reject [--reason]`, `request-evidence`, `revoke` commands.
  - Markdown render of pending requests.
- **Estimate:** 0.5 PR-day.

### v1.4.5-T1 — Audit event taxonomy
- **Dependencies:** v1.4.3-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/audit/__init__.py`
  - `src/safecode/enterprise/audit/events.py`
- **Tests:**
  - `tests/enterprise/audit/test_taxonomy_coverage.py`
- **Acceptance:**
  - Every event class is emitted by at least one workflow node or
    engine.
  - Event-name vocabulary matches
    `enterprise-docs/security-governance-plan.md`.
- **Estimate:** 0.5 PR-day.

### v1.4.5-T2 — Hash-chain integration
- **Dependencies:** v1.4.5-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/audit/chain.py`
- **Tests:**
  - `tests/enterprise/audit/test_hash_chain_intact.py`
- **Acceptance:**
  - Wraps `src/safecode/audit/logger.py`; no legacy modification.
  - Tampering with one event invalidates the chain.
- **Estimate:** 0.5 PR-day.

---

## v1.5–v2.0 Mid-Grain Backlog

Each item below is a coarse task. Before implementation, it will be
expanded into the same shape as v1.1–v1.4 tasks.

### v1.5 AgentOps Observability

### v1.5.1-T1 — TraceEvent schema and emitter
- **Dependencies:** v1.2.1-T2 (`NodeCost`, `TraceEventDraft`), v1.4.5-T1
  (`AuditEventKind` vocabulary overlap).
- **Files/Modules:**
  - `src/safecode/enterprise/trace/__init__.py`
  - `src/safecode/enterprise/trace/events.py`
  - `src/safecode/enterprise/trace/emitter.py`
- **Tests:**
  - `tests/enterprise/trace/test_event_schema.py`
  - `tests/enterprise/trace/test_emitter_idempotency.py`
- **Acceptance:**
  - `TraceEvent`, `TraceEventType`, and `TraceContext` match
    `enterprise-docs/agentops-observability-plan.md`.
  - Every event has `run_id`, `node_id`, `timestamp`, `type`,
    `payload`, and `redaction_applied`.
  - Emitter writes append-only `.sac/enterprise/runs/<run_id>/trace.jsonl`.
  - `event_id` is deterministic; re-emit is a no-op.
  - String payload fields are secret-redacted and capped at 2 KB.
- **Security constraints:**
  - Redaction runs before persistence via `src/safecode/context/redactor.py`.
  - Run directories are isolated under `runs_root`; path traversal rejected.
  - Atomic append (temp + rename) prevents partial events.
- **Non-goals:** OpenTelemetry export; timeline/dashboard (later tasks).
- **Estimate:** 0.75 PR-day.

### v1.5.1-T2 — Wire emitter into workflow nodes and approval engine
- **Dependencies:** v1.5.1-T1, v1.2.2-T1, v1.4.3-T1, v1.4.5-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/orchestrator.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/_helpers.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/*.py` (extend)
  - `src/safecode/enterprise/approvals/engine.py` (extend)
  - `src/safecode/enterprise/approvals/store.py` (extend)
- **Tests:**
  - `tests/enterprise/trace/test_workflow_emits_trace.py`
  - `tests/enterprise/trace/test_approval_emits_trace.py`
- **Acceptance:**
  - Orchestrator owns monotonic `seq` per run.
  - Each workflow node emits `node.start` and `node.end`.
  - Approval engine emits `approval.requested`, `approval.decided`,
    and `approval.consumed` where applicable.
  - Overlapping audit events share `event_id` with trace events.
- **Security constraints:**
  - Trace payloads never include raw secrets or full file contents.
  - Emitter is optional in tests via injection; production path always emits.
- **Non-goals:** Timeline assembly; CLI.
- **Estimate:** 0.75 PR-day.

### v1.5.2-T1 — Run timeline serializer
- **Dependencies:** v1.5.1-T2, v1.2.4-T1, v1.4.3-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/trace/timeline.py`
- **Tests:**
  - `tests/enterprise/trace/test_timeline_round_trip.py`
  - `tests/enterprise/trace/test_timeline_redaction.py`
- **Acceptance:**
  - Joins `trace.jsonl`, state checkpoint, and approval records into
    `timeline.json` per `agentops-observability-plan.md`.
  - `timeline_schema_version` present; two serializations are
    byte-identical.
  - Sensitive fields absent or marked `"redacted": true`.
- **Security constraints:**
  - Serializer reads only on-disk artifacts; no network.
  - Timeline never rehydrates excluded strict-profile fields.
- **Non-goals:** Binary export; live streaming.
- **Estimate:** 0.75 PR-day.

### v1.5.2-T2 — `sac enterprise trace export` CLI
- **Dependencies:** v1.5.2-T1.
- **Files/Modules:**
  - `src/safecode/cli_enterprise.py` (extend)
- **Tests:**
  - `tests/enterprise/cli/test_cli_trace_export.py`
- **Acceptance:**
  - `sac enterprise trace export <run_id> --json` writes timeline JSON.
  - Missing run fails closed with non-zero exit.
- **Security constraints:**
  - Export applies redaction profile (default strict).
  - No stdout leak of secrets on error paths.
- **Non-goals:** Zip bundles (v1.9).
- **Estimate:** 0.25 PR-day.

### v1.5.3-T1 — Markdown dashboard renderer
- **Dependencies:** v1.5.2-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/trace/render_markdown.py`
- **Tests:**
  - `tests/enterprise/trace/test_render_markdown_sections.py`
- **Acceptance:**
  - Sections: Summary, Timeline, Citations, Tool Calls, Approvals,
    Validation, Cost, Safety Invariants, Failures.
  - Citations include path, line range, score, permission verdict.
  - Renderer reads only `timeline.json`, not raw `trace.jsonl`.
- **Security constraints:**
  - No raw prompts or full file contents in Markdown output.
- **Non-goals:** Web UI; HTML renderer (v1.7+).
- **Estimate:** 0.5 PR-day.

### v1.5.3-T2 — `sac enterprise trace show` CLI
- **Dependencies:** v1.5.3-T1.
- **Files/Modules:**
  - `src/safecode/cli_enterprise.py` (extend)
- **Tests:**
  - `tests/enterprise/cli/test_cli_trace_show.py`
- **Acceptance:**
  - `sac enterprise trace show <run_id>` prints Markdown to stdout.
  - Optional `--out` writes file; unknown run exits non-zero.
- **Security constraints:**
  - Uses strict profile by default.
- **Non-goals:** `--format html` (later).
- **Estimate:** 0.25 PR-day.

### v1.5.4-T1 — Strict redaction default and debug-mode policy bit
- **Dependencies:** v1.5.1-T1, v1.4.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/trace/redaction.py`
  - `src/safecode/enterprise/policy/models.py` (extend)
  - `src/safecode/enterprise/trace/emitter.py` (extend)
  - `src/safecode/enterprise/trace/timeline.py` (extend)
- **Tests:**
  - `tests/enterprise/trace/test_redaction_strict_default.py`
  - `tests/enterprise/trace/test_redaction_debug_requires_policy.py`
- **Acceptance:**
  - `trace.export_profile` defaults to `strict`.
  - Strict: no field > 2 KB verbatim; raw prompts and full file
    contents excluded.
  - Debug requires `allow_debug_traces=true`; otherwise
    `DebugTraceNotAllowed`.
- **Security constraints:**
  - Tool inputs always redacted regardless of profile.
  - Eval lane forces strict (hook only; full eval in v1.6).
  - Write-time and export-time redaction both enforced.
- **Non-goals:** Customer-supplied redaction patterns (v1.9).
- **Estimate:** 0.75 PR-day.

### v1.6 Evaluation and Regression

### v1.6.1-T1 — EvaluationCase and EvaluationResult models
- **Dependencies:** v1.2.1-T2 (`RunCosts`, `NodeCost`), v1.5.2-T1 (`timeline.json`).
- **Files/Modules:**
  - `src/safecode/enterprise/eval/cases.py`
  - `src/safecode/enterprise/eval/exceptions.py`
  - `src/safecode/enterprise/eval/__init__.py` (extend)
- **Tests:**
  - `tests/enterprise/eval/test_case_schema.py`
- **Acceptance:**
  - `EvaluationCase` and `EvaluationResult` match `data-models.md`.
  - `CostBudget` defaults are deterministic.
  - YAML loads via `safe_load` only.
- **Security constraints:**
  - Case fixtures are untrusted data; never executed as instructions.
  - Result artifacts use strict redaction profile by default.
- **Non-goals:** Runner, baselines, CLI.
- **Estimate:** 0.5 PR-day.

### v1.6.1-T2 — Eval runner and case loader
- **Dependencies:** v1.6.1-T1, v1.5.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/eval/loader.py`
  - `src/safecode/enterprise/eval/runner.py`
- **Tests:**
  - `tests/enterprise/eval/test_runner_round_trip.py`
  - `tests/enterprise/eval/test_duplicate_case_id.py`
- **Acceptance:**
  - Discovers cases from `tests/enterprise/eval/cases/`.
  - Trivial smoke case completes in <2 s on mock provider.
  - Duplicate `case_id` raises `DuplicateCaseIdError`.
- **Security constraints:**
  - Mock provider only; no network in default lane.
  - Trace export profile forced to `strict`.
- **Non-goals:** Suite-specific workflow execution beyond smoke.
- **Estimate:** 0.75 PR-day.

### v1.6.2-T1 — Retrieval suite migration
- **Dependencies:** v1.6.1-T2, v1.1.4-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/eval/retrieval.py` (extend)
  - `src/safecode/enterprise/eval/runner.py` (extend)
- **Tests:**
  - `tests/enterprise/eval/test_retrieval_quality.py` (extend)
- **Acceptance:**
  - Retrieval cases run through unified runner and meet
    `retrieval_v1_1.json` baseline.
  - Forbidden sources never appear in top-k.
- **Security constraints:**
  - Retrieved content treated as untrusted input.
- **Non-goals:** New retrieval case categories beyond v1.1.4 set.
- **Estimate:** 0.5 PR-day.

### v1.6.3-T1 — Prompt-injection eval cases
- **Dependencies:** v1.6.1-T2.
- **Files/Modules:**
  - `tests/enterprise/eval/cases/prompt_injection/*.yaml`
  - `src/safecode/enterprise/eval/runner.py` (extend)
  - `src/safecode/enterprise/eval/assertions.py`
- **Tests:**
  - `tests/enterprise/eval/test_prompt_injection_suite.py`
- **Acceptance:**
  - At least eight categories from `evaluation-plan.md`.
  - Cases assert injection refusal via structured result fields.
- **Security constraints:**
  - Injection text in fixtures must not become workflow instructions.
  - Strict redaction on eval outputs.
- **Non-goals:** Non-English injection text.
- **Estimate:** 0.75 PR-day.

### v1.6.4-T1 — Tool-classification adversarial cases
- **Dependencies:** v1.6.1-T2, v1.3.5-T1.
- **Files/Modules:**
  - `tests/enterprise/eval/cases/tool_classification/*.yaml`
  - `src/safecode/enterprise/eval/runner.py` (extend)
- **Tests:**
  - `tests/enterprise/eval/test_tool_classification_suite.py`
- **Acceptance:**
  - Adversarial MCP metadata cannot upgrade tool tier to `AUTO`.
  - Malformed discovery yields `BLOCK` or typed errors.
- **Security constraints:**
  - Local allowlist remains authoritative over server metadata.
- **Non-goals:** In-process native-tool spoofing attacks.
- **Estimate:** 0.5 PR-day.

### v1.6.5-T1 — Dashboard and ratchet enforcement
- **Dependencies:** v1.6.2-T1, v1.6.3-T1, v1.6.4-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/eval/dashboard.py`
  - `src/safecode/enterprise/eval/ratchet.py`
  - `src/safecode/cli_enterprise.py` (extend)
  - `tests/enterprise/eval/baselines/*.json`
- **Tests:**
  - `tests/enterprise/eval/test_ratchet_enforcement.py`
  - `tests/enterprise/eval/test_eval_dashboard.py`
  - `tests/enterprise/cli/test_cli_eval_run.py`
- **Acceptance:**
  - `sac enterprise eval run --suite all` writes results and dashboard.
  - Baselines update only via `--update-baseline`.
  - Ratchet does not silently lower thresholds.
- **Security constraints:**
  - `.sac/enterprise/eval/latest.md` not committed.
  - Baseline files include date and commit metadata.
- **Non-goals:** Web dashboard; live-provider merge gate.
- **Estimate:** 0.75 PR-day.

### v1.7 PR Security Review MVP

### v1.7.1-T1 — `pr_review` sub-graph wiring
- **Dependencies:** v1.6 completed.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/tasks/pr_review.py`
  - `src/safecode/enterprise/workflow/nodes/collect_context.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/retrieve.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/analyze.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/plan.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/propose.py` (extend)
  - `examples/enterprise/fixtures/pr_sql_injection/`
- **Tests:**
  - `tests/enterprise/workflow/tasks/test_pr_review_happy_path.py`
  - `tests/enterprise/workflow/tasks/test_pr_review_no_findings.py`
- **Acceptance:**
  - Workflow consumes a PR fixture directory and retrieves citations.
  - SQL-injection fixture yields `high` risk and a report artifact.
- **Security constraints:**
  - Fixture paths cannot escape `repo_root`.
  - Retrieval remains permission-scoped.
- **Non-goals:** Live GitHub fetch (v1.7.3).
- **Estimate:** 1.0 PR-day.

### v1.7.1-T2 — Risk-tier assignment node logic
- **Dependencies:** v1.7.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/tasks/pr_review.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/analyze.py` (extend)
- **Tests:**
  - `tests/enterprise/workflow/tasks/test_pr_review_happy_path.py`
  - `tests/enterprise/eval/cases/pr_review/*.yaml`
- **Acceptance:**
  - Deterministic detectors for SQLi, secrets, deserialization, CVE refs.
  - Benign fixture maps to `low` with no findings.
- **Security constraints:**
  - Detectors are pattern-based; model output is not authority.
- **Non-goals:** ML classifiers.
- **Estimate:** 0.5 PR-day.

### v1.7.2-T1 — Report renderer with required sections
- **Dependencies:** v1.7.1-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/render_pr_report.py`
  - `src/safecode/enterprise/workflow/nodes/finalize.py` (extend)
- **Tests:**
  - `tests/enterprise/workflow/test_pr_report_render.py`
- **Acceptance:**
  - Markdown sections: Summary, Risk Findings, Cited Policies, Cited Code,
    Suggested Patch, Trace References.
- **Security constraints:**
  - Report uses redacted excerpts only.
- **Non-goals:** HTML export.
- **Estimate:** 0.5 PR-day.

### v1.7.3-T1 — GitHub PR comment writer (offline by default)
- **Dependencies:** v1.7.2-T1, v1.4 approvals.
- **Files/Modules:**
  - `src/safecode/enterprise/connectors/github_pr_write.py`
  - `src/safecode/enterprise/workflow/nodes/finalize.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/approval.py` (extend)
- **Tests:**
  - `tests/enterprise/connectors/test_github_pr_comment_gated.py`
  - `tests/enterprise/workflow/tasks/test_pr_review_approval_gate.py`
- **Acceptance:**
  - Without approval, live write is blocked and traced.
  - Fixture mode writes redacted body locally.
- **Security constraints:**
  - No network I/O in default offline mode.
  - Comment bodies redacted before persistence/trace.
- **Non-goals:** Real GitHub API calls.
- **Estimate:** 0.5 PR-day.

### v1.7.4-T1 — PR review eval cases (five)
- **Dependencies:** v1.7.1-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/eval/pr_review.py`
  - `tests/enterprise/eval/cases/pr_review/*.yaml`
  - `examples/enterprise/fixtures/pr_*/`
- **Tests:**
  - `tests/enterprise/eval/test_pr_review_suite.py`
- **Acceptance:**
  - Five cases: SQLi, secret, deserialization, CVE dep, benign.
  - Suite passes under mock workflow lane.
- **Security constraints:**
  - Eval forces strict trace profile.
- **Non-goals:** Live provider eval.
- **Estimate:** 0.75 PR-day.

### v1.7.4-T2 — PR review baseline
- **Dependencies:** v1.7.4-T1.
- **Files/Modules:**
  - `tests/enterprise/eval/baselines/pr_review_v1_7.json`
  - `src/safecode/cli_enterprise.py` (extend `eval run --suite pr_review`)
- **Tests:**
  - `tests/enterprise/eval/test_pr_review_suite.py`
- **Acceptance:**
  - Baseline checked in with date + commit metadata.
  - `sac enterprise eval run --suite pr_review` ratchets pass.
- **Security constraints:**
  - Baseline updates require explicit `--update-baseline`.
- **Non-goals:** Cross-suite merge gate.
- **Estimate:** 0.25 PR-day.

### v1.8 Vulnerability Remediation Workflow

### v1.8.1-T1 — Remediation task sub-graph
- **Dependencies:** v1.7 completed.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/tasks/remediation.py`
  - `src/safecode/enterprise/workflow/nodes/collect_context.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/retrieve.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/analyze.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/plan.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/propose.py` (extend)
  - `src/safecode/enterprise/workflow/orchestrator.py` (extend)
  - `examples/enterprise/fixtures/remediation/*/`
- **Tests:**
  - `tests/enterprise/workflow/tasks/test_remediation_ingest.py`
- **Acceptance:**
  - Workflow consumes a finding fixture directory and returns `SecurityFinding[]`.
  - RAG retrieval yields policy citations for known vulnerability types.
- **Security constraints:**
  - Fixture paths cannot escape `repo_root`.
  - Findings and code chunks treated as untrusted input.
- **Non-goals:** Live Semgrep invocation in workflow lane.
- **Estimate:** 1.0 PR-day.

### v1.8.2-T1 — Vulnerability classifier node
- **Dependencies:** v1.8.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/tasks/remediation.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/analyze.py` (extend)
- **Tests:**
  - `tests/enterprise/workflow/tasks/test_remediation_classifier.py`
- **Acceptance:**
  - Deterministic classifier maps fixture findings to vulnerability types.
  - SQL-injection fixture references secure-sql policy citation.
- **Security constraints:**
  - Classifier is pattern/rule-based; model output is not authority.
- **Non-goals:** ML classifiers.
- **Estimate:** 0.5 PR-day.

### v1.8.2-T2 — Fix planner node
- **Dependencies:** v1.8.2-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/tasks/remediation.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/plan.py` (extend)
- **Tests:**
  - `tests/enterprise/workflow/tasks/test_remediation_classifier.py`
- **Acceptance:**
  - Plan actions reference cited policy and target file for each fixture type.
- **Security constraints:**
  - Plan is a proposal only; no file writes.
- **Non-goals:** Multi-file refactor plans.
- **Estimate:** 0.5 PR-day.

### v1.8.3-T1 — Patch proposal with checkpoint wrapper
- **Dependencies:** v1.8.2-T2, v1.4 approvals.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/remediation_patch.py`
  - `src/safecode/enterprise/workflow/render_remediation_report.py`
  - `src/safecode/enterprise/workflow/nodes/propose.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/finalize.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/approval.py` (extend)
- **Tests:**
  - `tests/enterprise/workflow/test_patch_rollback.py`
- **Acceptance:**
  - Patch apply gated by approval; checkpoint created before apply.
  - Rejection or validation failure rolls back working tree by hash.
- **Security constraints:**
  - No automatic write; grants are single-use scoped.
- **Non-goals:** Live Git apply to remote.
- **Estimate:** 0.75 PR-day.

### v1.8.4-T1 — Validation node (test + scanner re-run)
- **Dependencies:** v1.8.3-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/workflow/tasks/remediation.py` (extend)
  - `src/safecode/enterprise/workflow/nodes/validate.py` (extend)
- **Tests:**
  - `tests/enterprise/workflow/test_validation_rerun.py`
- **Acceptance:**
  - Post-patch validation reports pass/fail with scanner diff metadata.
  - Validation cannot disable tests or pass with forbidden patch markers.
- **Security constraints:**
  - RC fixtures use deterministic in-process checks; any external scanner re-run
    must use the sandbox proposal pipeline and separate approval.
- **Non-goals:** Full CI reproduction.
- **Estimate:** 0.5 PR-day.

### v1.8.5-T1 — Remediation eval cases (five)
- **Dependencies:** v1.8.4-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/eval/remediation.py`
  - `tests/enterprise/eval/cases/remediation/*.yaml`
  - `tests/enterprise/eval/baselines/remediation_v1_8.json`
  - `examples/enterprise/demos/v1.8/remediation.md`
  - `src/safecode/cli_enterprise.py` (extend `eval run --suite remediation`)
- **Tests:**
  - `tests/enterprise/eval/test_remediation_suite.py`
  - `tests/enterprise/eval/test_remediation_baseline.py`
- **Acceptance:**
  - Five cases: SQLi, secret, unsafe eval, path traversal, dependency CVE.
  - Eval runs in isolated workspaces; committed fixtures remain pristine.
  - Baseline checked in; `sac enterprise eval run --suite remediation` ratchets pass.
- **Security constraints:**
  - Forbidden behaviors: disable tests, secret in patch.
  - Baseline updates require explicit `--update-baseline`.
- **Non-goals:** Cross-suite merge gate.
- **Estimate:** 0.75 PR-day.

### v1.9 Enterprise Beta Hardening

### v1.9.1-T1 — `tenant_id` propagation through RAG and audit
- **Dependencies:** v1.8 completed.
- **Files/Modules:**
  - `src/safecode/enterprise/policy/models.py` (extend `PolicySnapshot`)
  - `src/safecode/enterprise/policy/resolver.py` (extend)
  - `src/safecode/enterprise/audit/tenant.py`
  - `src/safecode/enterprise/audit/chain.py` (extend)
  - `src/safecode/enterprise/trace/session.py` (extend)
  - `src/safecode/enterprise/workflow/orchestrator.py` (extend `build_initial_state`)
  - `src/safecode/cli_enterprise.py` (extend `--tenant`)
- **Tests:**
  - `tests/enterprise/multitenant/test_tenant_isolation.py`
  - `tests/enterprise/multitenant/test_retrieval_tenant_filter.py`
- **Acceptance:**
  - Tenant A retrieval never returns tenant B chunks with matching content.
  - Audit events carry `tenant_id` and filter by tenant.
- **Security constraints:**
  - Cross-tenant access fails closed in RAG and audit reads.
- **Non-goals:** Per-tenant filesystem indexes.
- **Estimate:** 0.75 PR-day.

### v1.9.2-T1 — Evidence export CLI and zip schema
- **Dependencies:** v1.9.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/evidence/export.py`
  - `src/safecode/cli_enterprise.py` (extend `evidence export`)
- **Tests:**
  - `tests/enterprise/evidence/test_export_shape.py`
- **Acceptance:**
  - `sac enterprise evidence export --run <id>` produces zip with manifest,
    trace, timeline, citations, approvals, audit segment, validation.
  - Export verifies the anchored source audit chain; import verifies bundled event hashes.
- **Security constraints:**
  - Strict redaction profile; no debug artifacts unless policy allows.
- **Non-goals:** Multi-run batch export UI.
- **Estimate:** 0.75 PR-day.

### v1.9.3-T1 — Latency budget tests
- **Dependencies:** v1.9.2-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/perf/budgets.py`
  - `src/safecode/enterprise/eval/dashboard.py` (extend)
- **Tests:**
  - `tests/enterprise/perf/test_workflow_latency_budget.py`
- **Acceptance:**
  - PR review benign fixture completes < 30s on mock provider.
  - Eval dashboard surfaces latency budget warnings.
- **Security constraints:**
  - Budget checks are observability only; no policy weakening.
- **Non-goals:** Live provider latency SLOs.
- **Estimate:** 0.5 PR-day.

### v1.9.4-T1 — Status-line pass across planning docs
- **Dependencies:** v1.9.3-T1.
- **Files/Modules:**
  - `product-planning/*.md`
  - `enterprise-docs/*.md`
  - `examples/enterprise/demos/v1.9/beta_summary.md`
- **Tests:**
  - Manual review; no new code tests.
- **Acceptance:**
  - Every planning and enterprise doc shows v1.9 implementation status.
  - Beta demo walk-through checked in.
- **Security constraints:**
  - Doc-only; no behavior change.
- **Non-goals:** Web dashboard.
- **Estimate:** 0.5 PR-day.

### v2.0 Enterprise Release Candidate

### v2.0.1-T1 — Public contract snapshot test
- **Dependencies:** v1.9 completed.
- **Files/Modules:**
  - `src/safecode/enterprise/contracts/snapshot.py`
  - `tests/enterprise/contracts/test_public_contract_v2_0.py`
  - `tests/enterprise/contracts/snapshots/*.json`
- **Tests:**
  - `tests/enterprise/contracts/test_public_contract_v2_0.py`
- **Acceptance:**
  - CLI commands, trace schema, timeline schema, evidence manifest, eval baseline,
    and workflow state fields frozen in snapshots.
  - Contract drift fails CI until snapshots updated intentionally.
- **Security constraints:**
  - Snapshots exclude secrets and host-specific paths.
- **Non-goals:** Kernel contract migration from `tests/test_public_contract_snapshots.py`.
- **Estimate:** 0.75 PR-day.

### v2.0.2-T1 — External-style security review
- **Dependencies:** v2.0.1-T1.
- **Files/Modules:**
  - `enterprise-docs/security-review-v2-0.md`
  - `src/safecode/enterprise/approvals/store.py` (M1 remediation)
- **Tests:**
  - `tests/enterprise/approvals/test_request_store.py` (extend tamper case)
- **Acceptance:**
  - Review filed; no open high-severity findings.
  - M1 approval hash enforcement on list path closed.
- **Security constraints:**
  - M2-M3 approval binding and tenant propagation findings closed before RC.
- **Non-goals:** Hosted penetration test.
- **Estimate:** 0.75 PR-day.

### v2.0.3-T1 — Deployment-profile docs
- **Dependencies:** v2.0.2-T1.
- **Files/Modules:**
  - `enterprise-docs/deployment-profiles.md`
- **Tests:**
  - Doc review only.
- **Acceptance:**
  - Local, team server, and on-prem hybrid profiles documented with components,
    security posture, dependencies, limitations.
- **Security constraints:**
  - Plans only; no weakening of defaults.
- **Non-goals:** Implementation of hosted profiles.
- **Estimate:** 0.5 PR-day.

### v2.0.4-T1 — RC release notes and dashboard
- **Dependencies:** v2.0.3-T1.
- **Files/Modules:**
  - `RELEASE-NOTES-v2.0.0-rc.md`
  - `examples/enterprise/demos/v2.0/rc_dashboard.md`
- **Tests:**
  - Full regression + `scripts/verify-package.py`
- **Acceptance:**
  - Release notes link contract snapshot.
  - RC dashboard documents eval + trace gate commands.
- **Security constraints:**
  - Release notes reference security review doc.
- **Non-goals:** Git tag push (operator action).
- **Estimate:** 0.5 PR-day.

---

## v2.1 Team Server Foundation (planned)

Sub-plan ordering matches `version-roadmap.md`. Every v2.1 task is sized for a
single PR, lists files / contracts / persistence impact / security boundary /
positive and negative tests / acceptance / non-goals / rollback or compatibility
notes. The estimates are PR-days.

### v2.1.1-T1 — API and configuration contracts
- **Version:** v2.1.1
- **Title:** Land OpenAPI + settings + runtime-mode contracts for Team Server
- **Description:** Define the planned-status v2.1 service surface (OpenAPI spec,
  settings module, runtime-mode flag) before any handler ships. No live
  endpoints, no FastAPI handlers, no PostgreSQL access; this PR only freezes the
  contracts the rest of v2.1 will implement against.
- **Dependencies:** none beyond v2.0 RC.
- **Files/Modules:**
  - `enterprise-docs/platform-architecture-v2.md` (cross-link)
  - `src/safecode/enterprise/api/__init__.py` (planned skeleton; empty package)
  - `src/safecode/enterprise/api/contracts/openapi.yaml` (planned)
  - `src/safecode/enterprise/api/contracts/__init__.py` (planned)
  - `src/safecode/enterprise/api/settings.py` (planned, pydantic-settings only)
  - `tests/enterprise/api/test_contract_present.py` (planned)
- **Public contract:** new OpenAPI document, marked
  `x-status: planned`. Pinned by a snapshot test created later in v2.1.7-T1.
- **Persistence / migration impact:** none.
- **Security boundary:** introduces `runtime_mode` setting (`local` or
  `server`) and the auth provider configuration shape. Defaults to `local`
  so the CLI behavior is unchanged.
- **Positive tests:**
  - Settings parse a documented `.env.example` and produce a deterministic
    `RuntimeConfig`.
  - OpenAPI document parses with `yaml.safe_load` and has no `x-status:
    delivered` keys yet.
- **Negative tests:**
  - Missing required setting in `server` mode raises a typed validation error.
  - Conflicting auth and runtime mode combinations raise typed errors.
- **Acceptance:**
  - OpenAPI surface enumerates every endpoint listed in
    `platform-architecture-v2.md` § Service plane.
  - `runtime_mode` defaults to `local`; CLI behavior unchanged.
  - No live FastAPI app started.
- **Non-goals:** Any handler, any storage, any auth.
- **Estimate:** 0.75 PR-day.
- **Rollback / compatibility:** purely additive; revert restores v2.0 behavior.

### v2.1.1-T2 — Storage and worker decision (no code)
- **Version:** v2.1.1
- **Title:** Record the PostgreSQL+pgvector and durable-worker choices
- **Description:** Add the two architecture decisions to `decision-log.md`
  (`D19` and `D20`), update `platform-architecture-v2.md` data and workflow
  planes to reference them, and add a small dependency note to the planning
  README. This PR is documentation only.
- **Dependencies:** v2.1.1-T1.
- **Files/Modules:**
  - `product-planning/decision-log.md` (extend)
  - `enterprise-docs/platform-architecture-v2.md` (extend)
- **Public contract:** none.
- **Persistence / migration impact:** none.
- **Security boundary:** none directly; decisions inform later boundaries.
- **Tests:** none; planning-doc PR.
- **Acceptance:**
  - `D19` (PostgreSQL+pgvector) and `D20` (durable worker) are present with
    rationale, alternatives, consequences, and revisit triggers.
  - Architecture doc references the decisions where the planes are introduced.
- **Non-goals:** code; dependency changes.
- **Estimate:** 0.5 PR-day.
- **Rollback / compatibility:** doc-only; revert restores prior state.

### v2.1.1-T3 — Deployment scaffolding stub (planning only)
- **Version:** v2.1.1
- **Title:** Document the v2.1 deployment shape without committing infra files
- **Description:** Extend `deployment-profiles.md` Team Server section with a
  concrete component list (FastAPI, worker, PostgreSQL, optional pgvector
  later) plus a reference to the dev profile. No `docker-compose.yaml` lands
  yet; that file is added in v2.1.7-T1 when contracts are stable.
- **Dependencies:** v2.1.1-T2.
- **Files/Modules:**
  - `enterprise-docs/deployment-profiles.md` (extend)
- **Public contract:** none.
- **Persistence / migration impact:** none.
- **Security boundary:** unchanged.
- **Tests:** existing doc presence test extended for the new section.
- **Acceptance:** profile lists every component the rest of v2.1 will need.
- **Non-goals:** committed infra manifests.
- **Estimate:** 0.25 PR-day.
- **Rollback / compatibility:** doc-only; revert restores prior state.

### v2.1.2-T1 — Repository protocols
- **Version:** v2.1.2
- **Title:** Factor `Protocol` interfaces for runs, approvals, audit, evidence
- **Description:** Add typed `Protocol` classes describing every persistence
  surface currently spread across `.sac/enterprise/` writers. No behavior
  change; existing file-backed code remains the only implementation.
- **Dependencies:** v2.1.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/persistence/__init__.py` (planned)
  - `src/safecode/enterprise/persistence/protocols.py` (planned)
  - `tests/enterprise/persistence/test_protocols.py` (planned)
- **Public contract:** internal-only protocol shapes.
- **Persistence / migration impact:** none.
- **Security boundary:** protocols mandate `tenant_id` on every read and write.
- **Positive tests:** protocol classes are subclassable; concrete v2.0
  writers satisfy them via structural typing (`runtime_checkable`).
- **Negative tests:** missing `tenant_id` arguments raise typed errors.
- **Acceptance:** every write path used in v1.7 / v1.8 / v1.9 / v2.0 has a
  corresponding protocol method.
- **Non-goals:** any change to behavior or file layout.
- **Estimate:** 0.75 PR-day.
- **Rollback / compatibility:** additive.

### v2.1.2-T2 — Local backend adapter behind protocols
- **Version:** v2.1.2
- **Title:** Wrap existing `.sac/enterprise/` writers in the protocol surface
- **Description:** Add a `LocalBackend` class that implements every protocol
  using the existing on-disk layout; route v1.7 / v1.8 / v1.9 / v2.0 callers
  through the backend without changing observable behavior.
- **Dependencies:** v2.1.2-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/persistence/local_backend.py` (planned)
  - Callers across `workflow`, `approvals`, `evidence`, `audit`, `eval`
    routed through the backend instance.
- **Public contract:** unchanged; the same JSON shapes persist on disk.
- **Persistence / migration impact:** no schema change; same paths.
- **Security boundary:** all backend methods accept and enforce `tenant_id`.
- **Positive tests:** the full enterprise suite still passes; a contract
  test asserts equivalence with the v2.0 baseline JSON snapshots.
- **Negative tests:** writing to a path outside the run root fails closed.
- **Acceptance:** zero diff in evidence bundles for the v2.0 fixtures.
- **Non-goals:** PostgreSQL.
- **Estimate:** 1.25 PR-days.
- **Rollback / compatibility:** revert removes the backend indirection.

### v2.1.2-T3 — Backend-agnostic contract suite
- **Version:** v2.1.2
- **Title:** Reusable protocol contract tests for any backend
- **Description:** Add a parametrized suite that any backend (local file,
  later PostgreSQL) must pass. Exercises run lifecycle, approval lifecycle,
  audit append, evidence pack, single-use grant.
- **Dependencies:** v2.1.2-T2.
- **Files/Modules:**
  - `tests/enterprise/persistence/test_backend_contract.py` (planned)
- **Public contract:** none.
- **Persistence / migration impact:** none.
- **Security boundary:** tenant isolation tested per backend.
- **Acceptance:** local backend passes; harness ready for v2.1.3.
- **Non-goals:** none.
- **Estimate:** 0.5 PR-day.
- **Rollback / compatibility:** test-only.

### v2.1.3-T1 — PostgreSQL schema and migrations
- **Version:** v2.1.3
- **Title:** Define schema, indexes, and migrations under `safecode.enterprise.persistence.postgres`
- **Description:** Add the declarative SQL schema (runs, checkpoints,
  approvals, grants, audit_chain, evidence_index, eval_results) plus
  idempotent migrations. No data writes yet from production code.
- **Dependencies:** v2.1.2-T3, decision `D19`.
- **Files/Modules:**
  - `src/safecode/enterprise/persistence/postgres/__init__.py` (planned)
  - `src/safecode/enterprise/persistence/postgres/schema.sql` (planned)
  - `src/safecode/enterprise/persistence/postgres/migrations/` (planned)
  - `tests/enterprise/persistence/postgres/test_schema_round_trip.py` (planned)
- **Public contract:** SQL DDL; pinned by a snapshot test.
- **Persistence / migration impact:** introduces `enterprise` schema; no
  data migrated from filesystem in this task.
- **Security boundary:** every owned table requires non-null `tenant_id`.
- **Positive tests:** schema applies on an in-memory PG fake; migrations
  idempotent.
- **Negative tests:** missing `tenant_id` column fails the schema test.
- **Acceptance:** schema covers every persistence protocol method.
- **Non-goals:** runtime adapter (`v2.1.3-T2`); pgvector (`v2.4`).
- **Estimate:** 1.0 PR-day.
- **Rollback / compatibility:** schema file additive; no caller depends on it.

### v2.1.3-T2 — PostgreSQL repository adapter
- **Version:** v2.1.3
- **Title:** Implement persistence protocols against PostgreSQL
- **Description:** Add `PostgresBackend` that satisfies the v2.1.2 protocols
  using `psycopg` connections and a session-scoped unit of work. Tests use
  an in-memory PG fake to keep determinism; integration tests are opt-in.
- **Dependencies:** v2.1.3-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/persistence/postgres/backend.py` (planned)
  - `src/safecode/enterprise/persistence/postgres/unit_of_work.py` (planned)
  - `tests/enterprise/persistence/postgres/test_backend_contract.py` (planned)
- **Public contract:** internal.
- **Persistence / migration impact:** first runtime writer for the schema.
- **Security boundary:** every query parameterizes `tenant_id`; reads
  outside the scoped tenant fail closed.
- **Positive tests:** v2.1.2-T3 contract suite passes against the fake.
- **Negative tests:** cross-tenant read raises typed `TenantBoundaryError`.
- **Acceptance:** contract parity with the local backend.
- **Non-goals:** any service code.
- **Estimate:** 1.25 PR-days.
- **Rollback / compatibility:** removing the file restores the local-only
  state.

### v2.1.3-T3 — Atomic approval consumption
- **Version:** v2.1.3
- **Title:** Enforce single-use grant semantics under concurrent writers
- **Description:** Use `SERIALIZABLE` (or explicit row locks) for grant
  consumption so two workers cannot double-spend a grant.
- **Dependencies:** v2.1.3-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/persistence/postgres/backend.py` (extend)
  - `tests/enterprise/persistence/postgres/test_grant_concurrency.py` (planned)
- **Public contract:** internal.
- **Persistence / migration impact:** none.
- **Security boundary:** preserves the M2 binding from
  `security-review-v2-0.md` under concurrency.
- **Positive tests:** N concurrent workers see exactly one successful
  consumption; others get `GrantAlreadyConsumedError`.
- **Negative tests:** retried consume of a closed grant fails closed.
- **Acceptance:** concurrency test reliably reproduces the race and never
  leaks a second use.
- **Non-goals:** distributed locking; cluster-aware leases.
- **Estimate:** 0.75 PR-day.
- **Rollback / compatibility:** isolation level can revert; tests fail
  loud rather than silently weakening.

### v2.1.3-T4 — Audit chain durability under PostgreSQL
- **Version:** v2.1.3
- **Title:** Persist the audit hash chain to PostgreSQL with verification
- **Description:** Append the existing audit events to a row-per-event
  table while preserving the legacy hash chain. Verification runs against
  both local file and PG backends.
- **Dependencies:** v2.1.3-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/persistence/postgres/audit.py` (planned)
  - `tests/enterprise/persistence/postgres/test_audit_chain.py` (planned)
- **Public contract:** internal.
- **Persistence / migration impact:** dedicated table; chain unchanged.
- **Security boundary:** tampering invalidates the chain on read.
- **Acceptance:** chain verifies on both backends; tampering test
  passes.
- **Non-goals:** external anchors.
- **Estimate:** 0.75 PR-day.

### v2.1.4-T1 — FastAPI app skeleton and health endpoints
- **Version:** v2.1.4
- **Title:** Boot FastAPI app with health, readiness, and version endpoints
- **Description:** Add an application factory wired to the v2.1 settings,
  with no business endpoints. Establishes the dependency-injection pattern
  for backends and identity.
- **Dependencies:** v2.1.3-T2, v2.1.1-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/api/app.py` (planned)
  - `src/safecode/enterprise/api/dependencies.py` (planned)
  - `tests/enterprise/api/test_health.py` (planned)
- **Public contract:** `/healthz`, `/readyz`, `/version`.
- **Persistence / migration impact:** readiness check probes the active
  backend.
- **Security boundary:** unauthenticated probes only; no business data.
- **Positive tests:** health returns deterministic body; readiness depends
  on backend probe.
- **Negative tests:** broken backend produces `503`.
- **Acceptance:** app boots in test client against the local backend.
- **Non-goals:** business endpoints.
- **Estimate:** 0.5 PR-day.

### v2.1.4-T2 — Read endpoints (runs, approvals, traces, evidence, eval)
- **Version:** v2.1.4
- **Title:** GET endpoints for the operator surface
- **Description:** Add read-only endpoints that return tenant-scoped lists
  and details for runs, approvals, traces, evidence bundles, and eval
  baselines. Handlers share the existing redaction profile.
- **Dependencies:** v2.1.4-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/api/routes/runs.py` (planned)
  - `src/safecode/enterprise/api/routes/approvals.py` (planned)
  - `src/safecode/enterprise/api/routes/traces.py` (planned)
  - `src/safecode/enterprise/api/routes/evidence.py` (planned)
  - `src/safecode/enterprise/api/routes/eval.py` (planned)
  - `tests/enterprise/api/test_read_endpoints.py` (planned)
- **Public contract:** OpenAPI documents finalized for GET endpoints.
- **Persistence / migration impact:** read-only.
- **Security boundary:** authenticated subject required; tenant-scoped
  query parameters; no debug profile exposed by default.
- **Positive tests:** valid token returns expected list and details.
- **Negative tests:** missing / cross-tenant tokens fail closed; debug
  fields absent without policy bit.
- **Acceptance:** every read endpoint covered by positive and negative
  cases.
- **Non-goals:** writes, approvals, command endpoints.
- **Estimate:** 1.0 PR-day.

### v2.1.5-T1 — Command endpoints for runs
- **Version:** v2.1.5
- **Title:** POST endpoints to start, resume, and cancel runs
- **Description:** Add command endpoints that hand off to the durable
  worker queue with explicit idempotency keys.
- **Dependencies:** v2.1.4-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/api/routes/runs.py` (extend)
  - `src/safecode/enterprise/worker/__init__.py` (planned)
  - `src/safecode/enterprise/worker/queue.py` (planned)
  - `tests/enterprise/api/test_run_commands.py` (planned)
- **Public contract:** API extensions; OpenAPI updated.
- **Persistence / migration impact:** new `run_commands` and `queue` tables.
- **Security boundary:** idempotency key required; only the owning tenant
  may start or cancel a run; protected actions still routed through the
  approval engine.
- **Positive tests:** same idempotency key returns the same run_id; cancel
  is a graceful no-op when the run is already terminal.
- **Negative tests:** missing idempotency key fails closed; cross-tenant
  cancel rejected.
- **Acceptance:** command surface matches OpenAPI snapshot.
- **Non-goals:** webhook ingestion.
- **Estimate:** 1.0 PR-day.

### v2.1.5-T2 — Command endpoint for approvals
- **Version:** v2.1.5
- **Title:** POST endpoint to submit approval decisions
- **Description:** Mirror the CLI approval verbs through the API. Single-
  use grants are issued through the same engine.
- **Dependencies:** v2.1.5-T1, v2.1.3-T3.
- **Files/Modules:**
  - `src/safecode/enterprise/api/routes/approvals.py` (extend)
  - `tests/enterprise/api/test_approval_commands.py` (planned)
- **Public contract:** API extension; OpenAPI updated.
- **Persistence / migration impact:** uses existing approval and grant
  tables.
- **Security boundary:** subject identity must match an `approver`
  role per the role-permission matrix; self-approval blocked.
- **Positive tests:** approve / reject / revoke flows complete and emit
  audit events.
- **Negative tests:** unauthorized role fails closed; replay attack with
  a consumed grant rejected.
- **Acceptance:** identical behavior between CLI and API.
- **Non-goals:** notifications.
- **Estimate:** 0.75 PR-day.

### v2.1.5-T3 — Worker lease, heartbeat, and recovery
- **Version:** v2.1.5
- **Title:** Durable worker with lease, heartbeat, and crash recovery
- **Description:** Add a single worker implementation that pulls from the
  queue, leases a run, heartbeats, and releases the lease on crash.
- **Dependencies:** v2.1.5-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/worker/lease.py` (planned)
  - `src/safecode/enterprise/worker/runner.py` (planned)
  - `tests/enterprise/worker/test_lease_recovery.py` (planned)
- **Public contract:** internal.
- **Persistence / migration impact:** `lease` table with expiry index.
- **Security boundary:** workers see only data the API would expose to
  their identity.
- **Positive tests:** lease acquired and released atomically; heartbeat
  refreshes expiry; second worker takes over after crash.
- **Negative tests:** double-acquire blocked; expired lease auto-released.
- **Acceptance:** crash recovery deterministic in tests.
- **Non-goals:** scheduler quality of service.
- **Estimate:** 1.25 PR-days.

### v2.1.5-T4 — CLI thin-client mode
- **Version:** v2.1.5
- **Title:** Teach the CLI to route through the v2.1 API in `server` mode
- **Description:** Add a runtime-mode switch so the CLI runs against the
  filesystem locally and against the API in server mode. CLI contract is
  unchanged.
- **Dependencies:** v2.1.5-T2.
- **Files/Modules:**
  - `src/safecode/cli_enterprise.py` (extend)
  - `tests/enterprise/cli/test_cli_server_mode.py` (planned)
- **Public contract:** CLI behavior unchanged; new `--server-url` and
  `--token` flags; `local` mode default.
- **Persistence / migration impact:** none direct.
- **Security boundary:** `--token` accepted only in `server` mode and is
  redacted from logs.
- **Positive tests:** same fixture run produces same artifacts in both
  modes.
- **Negative tests:** `server` mode without a token fails closed.
- **Acceptance:** parity test between modes for the v1.7 fixture.
- **Non-goals:** auth provider login flow.
- **Estimate:** 0.75 PR-day.

### v2.1.6-T1 — OIDC discovery and JWT validation
- **Version:** v2.1.6
- **Title:** Validate bearer tokens against an OIDC provider
- **Description:** Add token validation using OIDC discovery and JWKS, with
  bounded clock skew and a small in-memory cache for keys.
- **Dependencies:** v2.1.4-T2.
- **Files/Modules:**
  - `src/safecode/enterprise/auth/__init__.py` (planned)
  - `src/safecode/enterprise/auth/oidc.py` (planned)
  - `tests/enterprise/auth/test_oidc.py` (planned)
- **Public contract:** internal.
- **Persistence / migration impact:** none (in-memory cache only).
- **Security boundary:** invalid or unsigned tokens fail closed; algorithm
  pinned to a configured allowlist.
- **Positive tests:** valid token resolves to a claims object.
- **Negative tests:** expired, tampered, or wrong-audience tokens rejected.
- **Acceptance:** unit-tested without network using a JWKS fixture.
- **Non-goals:** SSO provisioning.
- **Estimate:** 1.0 PR-day.

### v2.1.6-T2 — Authenticated subject mapping
- **Version:** v2.1.6
- **Title:** Map OIDC claims to the existing `RBACSubject`
- **Description:** Resolve the v2.1.6-T1 claims into the existing v1.4
  RBAC subject (tenant + role) and apply across API and worker contexts.
- **Dependencies:** v2.1.6-T1.
- **Files/Modules:**
  - `src/safecode/enterprise/auth/subject.py` (planned)
  - `tests/enterprise/auth/test_subject_mapping.py` (planned)
- **Public contract:** the existing `RBACSubject` shape.
- **Persistence / migration impact:** none.
- **Security boundary:** unknown claims default to the lowest role; the
  CLI `--actor` is ignored when an authenticated subject is present.
- **Positive tests:** known claim maps to the expected role; tenant id
  propagates.
- **Negative tests:** missing tenant claim fails closed in `server` mode.
- **Acceptance:** v2.1.4-T2 endpoint tests now use the resolved subject.
- **Non-goals:** SCIM provisioning.
- **Estimate:** 0.5 PR-day.

### v2.1.7-T1 — API and CLI contract snapshots
- **Version:** v2.1.7
- **Title:** Freeze the v2.1 API and CLI contracts
- **Description:** Extend the v2.0 contract snapshot tests to cover the
  new API surface, including OpenAPI digest, error shapes, and the CLI
  `--server-url` / `--token` flags.
- **Dependencies:** v2.1.6-T2.
- **Files/Modules:**
  - `tests/enterprise/contracts/test_public_contract_v2_1.py` (planned)
  - `tests/enterprise/contracts/snapshots/api_v2_1.json` (planned)
- **Public contract:** v2.1 frozen surface.
- **Persistence / migration impact:** none.
- **Security boundary:** snapshots scrub secrets and host-specific paths.
- **Acceptance:** drift fails CI until intentional snapshot update.
- **Non-goals:** GA contract (v3.0).
- **Estimate:** 0.5 PR-day.

### v2.1.7-T2 — Upgrade and rollback runbook
- **Version:** v2.1.7
- **Title:** Document upgrade and rollback from v2.0 to v2.1
- **Description:** Extend `deployment-profiles.md` and add an upgrade /
  rollback section anchored on v2.1.3 migrations and v2.1.2 backend swap.
- **Dependencies:** v2.1.7-T1.
- **Files/Modules:**
  - `enterprise-docs/deployment-profiles.md` (extend)
- **Public contract:** none.
- **Acceptance:** runbook covers schema apply, data migration from local
  to PostgreSQL, and rollback steps.
- **Non-goals:** chaos drills.
- **Estimate:** 0.5 PR-day.

### v2.1.7-T3 — v2.1 demo and integration suite
- **Version:** v2.1.7
- **Title:** Demo bundle + offline integration suite
- **Description:** Ship the v2.1 demo (under `examples/enterprise/demos/v2.1/`)
  plus a deterministic offline integration suite that runs against the API
  app and the PG fake.
- **Dependencies:** v2.1.7-T2.
- **Files/Modules:**
  - `examples/enterprise/demos/v2.1/` (planned)
  - `tests/enterprise/api/test_integration_v2_1.py` (planned)
- **Acceptance:** demo replays cleanly; integration suite green in CI.
- **Non-goals:** UI; webhook ingest.
- **Estimate:** 0.75 PR-day.

---

## v2.2 Real GitHub Secure Change Workflow (planned)

PR-sized; estimates and security boundaries as for v2.1.

### v2.2.1-T1 — GitHub App credential boundary
- **Files/Modules:** `src/safecode/enterprise/connectors/github_app.py` (planned),
  `src/safecode/enterprise/api/settings.py` (extend),
  `tests/enterprise/connectors/test_github_app_credentials.py` (planned).
- **Public contract:** environment / vault contract for the App private key.
- **Persistence / migration impact:** none.
- **Security boundary:** private key never written to disk, logs, traces, or
  evidence; reload requires explicit restart.
- **Acceptance:** secret never appears in any captured output; rotation test
  proves a refresh re-reads the key.
- **Non-goals:** webhook handler.
- **Estimate:** 0.75 PR-day.

### v2.2.1-T2 — Signed-webhook handler
- **Files/Modules:** `src/safecode/enterprise/api/routes/webhooks.py` (planned),
  `tests/enterprise/api/test_webhooks.py` (planned).
- **Public contract:** new `/webhooks/github` endpoint.
- **Persistence / migration impact:** `webhook_events` table.
- **Security boundary:** signature verification mandatory; missing secret
  fails closed.
- **Acceptance:** replay of the same delivery id is a no-op.
- **Non-goals:** PR fetch.
- **Estimate:** 0.75 PR-day.

### v2.2.2-T1 — Live PR fetch adapter
- **Files/Modules:** `src/safecode/enterprise/connectors/github_pr.py` (extend),
  `tests/enterprise/connectors/test_github_pr_live.py` (planned).
- **Public contract:** unchanged `PullRequestEvidence` shape.
- **Security boundary:** rate-limit and 4xx handling fail closed; out-of-tenant
  repository access rejected.
- **Acceptance:** offline fixture and recorded live response produce the same
  evidence.
- **Non-goals:** writes.
- **Estimate:** 0.75 PR-day.

### v2.2.2-T2 — Sandboxed PR checkout
- **Files/Modules:** `src/safecode/enterprise/sandbox/pr_workspace.py` (planned),
  `tests/enterprise/sandbox/test_pr_workspace.py` (planned).
- **Public contract:** internal.
- **Security boundary:** workspace pinned under the sandbox root; symlink
  escape rejected.
- **Acceptance:** checkout is read-only by default; mutation requires the
  v2.0 sandbox proposal pipeline.
- **Estimate:** 1.0 PR-day.

### v2.2.3-T1 — Governed PR comment write
- **Files/Modules:** `src/safecode/enterprise/connectors/github_pr_write.py`
  (extend), `tests/enterprise/connectors/test_github_pr_comment_live.py`
  (planned).
- **Security boundary:** write only after a single-use grant; comment body
  redacted; audit chain includes the API response id.
- **Acceptance:** unapproved write attempts always fail closed.
- **Estimate:** 0.75 PR-day.

### v2.2.3-T2 — Branch push and PR create
- **Files/Modules:** `src/safecode/enterprise/connectors/github_branch.py`
  (planned), `tests/enterprise/connectors/test_github_branch.py` (planned).
- **Security boundary:** protected branches stay `BLOCK`; pushed branches
  carry the v2.0 redaction profile.
- **Acceptance:** push and PR create paths gated; protected-branch attempt
  produces an audit event.
- **Estimate:** 1.0 PR-day.

### v2.2.4-T1 — Sandboxed scanner re-run
- **Files/Modules:** `src/safecode/enterprise/scanners/ci_runner.py` (planned),
  `tests/enterprise/scanners/test_ci_runner.py` (planned).
- **Security boundary:** every command goes through the sandbox proposal
  pipeline.
- **Acceptance:** CI runner refuses to run without an approved proposal.
- **Estimate:** 0.75 PR-day.

### v2.2.4-T2 — CI callback endpoint and structured result schema
- **Files/Modules:** `src/safecode/enterprise/api/routes/ci_callback.py`
  (planned), `src/safecode/enterprise/scanners/results.py` (planned),
  `tests/enterprise/api/test_ci_callback.py` (planned).
- **Security boundary:** callback authenticated; payload validated against
  schema; never treated as instructions.
- **Acceptance:** schema mismatches rejected; trace shows callback origin.
- **Estimate:** 0.75 PR-day.

### v2.2.5-T1 — End-to-end live PR review demo
- **Files/Modules:** `examples/enterprise/demos/v2.2/pr_review_live.md`
  (planned), `tests/enterprise/integration/test_pr_review_v2_2.py` (planned).
- **Acceptance:** demo runs against a sample repo; offline integration test
  passes; live test opt-in only.
- **Estimate:** 1.0 PR-day.

### v2.2.5-T2 — End-to-end live remediation demo
- **Files/Modules:** `examples/enterprise/demos/v2.2/remediation_live.md`
  (planned), `tests/enterprise/integration/test_remediation_v2_2.py`
  (planned).
- **Acceptance:** demo opens a real PR through the approval chain; integration
  test deterministic on fixtures.
- **Estimate:** 1.0 PR-day.

---

## v2.3 Operator Console (planned, mid-grain)

Tasks here cover the surfaces; each will be expanded into PR-sized items
before implementation. The `v2.3` console is bounded by the v2.1 API; no
backend mutation lives in the UI.

### v2.3.1-T1 — Console shell, OIDC login, tenant-aware navigation
- Acceptance: routed pages reject cross-tenant access; auth refresh works.

### v2.3.2-T1 — Run list and detail with trace viewer
- Acceptance: timeline renders the v1.5 schema; redaction profile honored.

### v2.3.3-T1 — Approval inbox and patch / comment review
- Acceptance: approval submit uses the v2.1.5-T2 endpoint; single-use grant
  semantics preserved.

### v2.3.4-T1 — Evidence, eval, and cost surfaces
- Acceptance: read-only; export reuses v1.9 evidence bundle endpoint.

### v2.3.5-T1 — UI / API contract snapshot and v2.3 demo bundle
- Acceptance: contract snapshot extended; demo recording committed.

---

## v2.4 Enterprise Knowledge, Tickets, and Memory (planned, mid-grain)

### v2.4.1-T1 — pgvector schema and migration
- Acceptance: tenant-scoped vector index; deterministic test harness.

### v2.4.2-T1 — Incremental ingest and freshness propagation
- Acceptance: no-op re-ingest on unchanged input; ACL sync verified.

### v2.4.3-T1 — Deterministic reranker and query rewriting
- Acceptance: ratchet enforced on retrieval suites.

### v2.4.4-T1 — Live Jira connector behind approval gate
- Acceptance: tenant-scoped credentials; write actions require GATE.

### v2.4.5-T1 — `secure_planning` workflow end-to-end
- Acceptance: planning artifact carries citations, alternatives, revisit.

### v2.4.6-T1 — Governed long-term memory
- Acceptance: admit/revoke/expire and audit trail proven.

---

## v2.5 Production Hardening (planned, mid-grain)

### v2.5.1-T1 — OpenTelemetry exporter behind the trace emitter
- Acceptance: exporter disable preserves local trace files.

### v2.5.2-T1 — Worker recovery and dead-letter behavior
- Acceptance: poisoned message reaches DLQ; healthy workers continue.

### v2.5.3-T1 — Concurrency, rate-limit, and cost budget controls
- Acceptance: documented limits enforced; cost budget tested against
  `RunCosts`.

### v2.5.4-T1 — Backup / restore and schema migration tooling
- Acceptance: round-trip across a schema migration; audit and evidence
  verifications succeed.

### v2.5.5-T1 — Load and threat model captured in `enterprise-docs/`
- Acceptance: ratchet on key endpoints; threat model includes v2.1+ new
  boundaries.

### v2.5.6-T1 — On-prem deploy automation and upgrade / rollback rehearsal
- Acceptance: single-command bring-up; rehearsed upgrade and rollback.

---

## v3.0 Enterprise GA (planned, mid-grain)

### v3.0.1-T1 — GA contract and migration compatibility tests
- Acceptance: v2.0 → v3.0 migration test green.

### v3.0.2-T1 — Signed external security review
- Acceptance: review filed; no open high / critical findings.

### v3.0.3-T1 — Production deployment evidence
- Acceptance: production-like deployment captured per profile.

### v3.0.4-T1 — Flagship demos and GA release notes
- Acceptance: demos repeat v2.2 acceptance against GA contracts.

---

## Backlog Hygiene

- Every merged PR must update this file by either marking the task
  as done (add a `Done in <commit>` line) or, if scope changed,
  editing the acceptance criteria with a Decision note linking to
  `decision-log.md`.
- New tasks must follow the same shape. Reject PRs that add tasks
  without IDs, files, tests, and acceptance.
- A task may be split if it grows past 1.5 PR-days; never grow
  beyond that without explicit rationale.
