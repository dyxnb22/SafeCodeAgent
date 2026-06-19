# Implementation Backlog

**Implementation status (v1.9):** Executable contracts through v1.9 are implemented; see `.agents/context/progress.json` for live stage state.
## Foundation

- Add `enterprise` package boundaries without disturbing existing CLI behavior.
- Define `EnterpriseRunState` with task type, actor, repo, policy context,
  retrieval evidence, planned actions, approvals, validation, and report fields.
- Add schema snapshots for all new run-state and node-output models.
- Keep legacy `sac` workflows green while adding Enterprise commands behind an
  experimental entrypoint.

## RAG

- Create a knowledge source registry for local docs, policy files, code chunks,
  historical fixes, and scanner findings.
- Extend existing chunking and embedding store work into a permission-aware
  retrieval layer.
- Add hybrid retrieval with keyword, semantic, git recency, pinned files, and
  metadata filters.
- Add citation objects with source path, line range, source type, score, and
  permission verdict.
- Add retrieval eval fixtures for policy recall and code localization.

## LangGraph Workflow

- Model the MVP workflow as explicit nodes before wiring LangGraph:
  classify, retrieve, analyze, plan, propose, validate, approve, finalize.
- Add node contracts using Pydantic models.
- Add checkpoint persistence and resume tests.
- Add conditional transitions for missing evidence, failed validation, high
  risk, and user rejection.
- Add human interrupt integration for approval-required nodes.

## Tools And MCP

- Inventory existing native tools and classify them for Enterprise workflows:
  read, write, command, network read, network write, scanner, ticketing, CI.
- Keep approval metadata outside server-controlled MCP payloads.
- Add MCP connector wrappers with capability scopes and output redaction.
- Add dry-run previews for GitHub and ticketing writes.
- Add tests that malicious tool output cannot change classification.

## Security Governance

- Add organization policy layer above user and project config.
- Add RBAC model for read, write, command, GitHub write, scanner, and admin
  actions.
- Add approval tiers for report-only, local patch, branch push, PR creation,
  scanner execution, and production-like actions.
- Add prompt-injection test fixtures for retrieved docs, MCP responses, issue
  text, and PR comments.
- Add audit events for workflow state transitions, retrieval citation use, and
  approval decisions.

## Observability And Evaluation

- Add enterprise run timeline renderer.
- Emit trace events for node start/end, model calls, tool calls, retrieval,
  approvals, validation, and failures.
- Track cost and token budgets per run and per node.
- Add a Markdown dashboard for MVP runs before building a web UI.
- Extend live eval with retrieval, approval, and scanner scenarios.

## Frontend Or Dashboard

- Start with generated Markdown/HTML reports.
- Add a focused dashboard only after traces and run schemas are stable.
- First views: run timeline, evidence panel, approval inbox, risk report,
  validation results, and cost summary.

## Documentation

- Keep high-signal Enterprise docs in `enterprise-docs/`.
- Keep roadmap and task planning in `product-planning/`.
- Do not restore old version notes in this branch.
- At Enterprise封版, compare with `archive/safecodeagent-final` and merge only
  still-relevant legacy docs into final `docs/`.
