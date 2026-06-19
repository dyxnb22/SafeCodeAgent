# Execution Backlog

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
- v1.8.1-T1 — Remediation task sub-graph.
- v1.8.2-T1 — Vulnerability classifier node.
- v1.8.2-T2 — Fix planner node.
- v1.8.3-T1 — Patch proposal with checkpoint wrapper.
- v1.8.4-T1 — Validation node (test + scanner re-run).
- v1.8.5-T1 — Remediation eval cases (five).

### v1.9 Enterprise Beta Hardening
- v1.9.1-T1 — `tenant_id` propagation through RAG and audit.
- v1.9.2-T1 — Evidence export CLI and zip schema.
- v1.9.3-T1 — Latency budget tests.
- v1.9.4-T1 — Status-line pass across planning docs.

### v2.0 Enterprise Release Candidate
- v2.0.1-T1 — Public contract snapshot test.
- v2.0.2-T1 — Run `/code-review ultra` and file findings.
- v2.0.3-T1 — Deployment-profile docs.
- v2.0.4-T1 — RC release notes and dashboard.

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
