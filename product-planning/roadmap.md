# Enterprise Roadmap

## Phase 0: Branch Cleanup And Planning

Goal: make this branch a focused Enterprise workspace.

Deliverables:
- Extract reusable SafeCodeAgent knowledge into `enterprise-docs/`.
- Remove legacy docs from this branch after extraction.
- Add `AGENTS.md`, `.cursorignore`, and a short `docs/README.md`.
- Keep `main` and `archive/safecodeagent-final` as legacy reference branches.

Exit criteria:
- New contributors can identify the Enterprise direction without reading old
  version history.
- Cursor and agent tools default to `product-planning/`, `enterprise-docs/`,
  `src/`, and `tests/`.

## Phase 1: MVP Security Workflow Agent

Goal: handle one complete security workflow from finding/PR input to auditable
report and optional patch proposal.

Scope:
- Input types: local repo path, PR diff, or structured security finding JSON.
- RAG sources: local security policy docs, code snippets, README/API docs, and
  small historical-fix fixtures.
- Workflow: classify task, retrieve context, analyze risk, generate plan,
  propose patch/report, run tests/scanners, request approval for mutation.
- Observability: run timeline with model calls, tool calls, retrieval citations,
  cost, latency, approval decisions, and validation outcomes.

Implementation themes:
- Introduce a workflow state model before adding LangGraph dependencies.
- Wrap existing SafeCode tools as workflow nodes.
- Keep existing write, command, GitHub, sandbox, and MCP gates intact.
- Add retrieval evaluation fixtures alongside existing coding evals.

Exit criteria:
- Demo can analyze a PR-like fixture, cite policy and code evidence, propose a
  minimal fix, run validation, and produce a report.
- No write path bypasses checkpoint, rollback, audit, or approval.

## Phase 2: LangGraph Orchestration And HITL

Goal: move from a linear agent loop to resumable enterprise workflows.

Scope:
- LangGraph StateGraph for security review and vulnerability remediation.
- Conditional edges for missing context, failed validation, high-risk action,
  and human approval.
- Checkpointed workflow state that can resume after interruption.
- Human-in-the-loop inbox for approve, reject, edit, or request more evidence.
- Structured node outputs with schema validation and retry policy.

Exit criteria:
- A workflow can pause before a high-risk operation and resume from the same
  state after approval.
- Failed retrieval, malformed model output, and failed validation produce
  explicit recoverable states.

## Phase 3: Enterprise Integrations

Goal: connect the workflow to realistic enterprise systems without weakening
local safety.

Scope:
- MCP connectors for GitHub, Jira/Linear, CI, document stores, and scanners.
- Organization-level policy config layered above user and project config.
- RBAC for tools and approval tiers.
- GitHub PR creation and branch push remain explicit approval actions.
- Scanner integrations for Semgrep, dependency audit, secrets scanning, and
  optional SAST imports.

Exit criteria:
- Integrations are capability-scoped and audit-logged.
- Network and write tools fail closed unless configured and approved.

## Phase 4: AgentOps And Evaluation Platform

Goal: make behavior measurable, debuggable, and regression-tested.

Scope:
- Trace dashboard for every node, tool, retrieval result, approval, and cost.
- Retrieval metrics: recall, citation grounding, stale-document detection, and
  reranker impact.
- Security workflow evals: PR review, SAST remediation, secrets handling,
  prompt injection, command refusal, and branch protection.
- Live provider lane remains opt-in until clean evidence justifies promotion.

Exit criteria:
- Release readiness is based on eval snapshots and dashboard artifacts, not
  anecdotal demos.
- Safety invariants are visible in every workflow report.

## Phase 5: Enterprise Hardening

Goal: make the platform credible for multi-user and team deployments.

Scope:
- Multi-tenant project and organization model.
- Central audit export and compliance reports.
- Secret and PII controls for retrieval, traces, and debug bundles.
- Deployment profiles for local, server, and hybrid execution.
- Policy-as-code for tool access, network allowlists, and approval tiers.

Exit criteria:
- The platform can explain who approved an action, why it was allowed, what
  evidence was used, what changed, and how validation passed.
