# LangGraph Workflow Design

**Implementation status (v1.9):** Executable contracts through v1.9 are implemented; see `.agents/context/progress.json` for live stage state.
## Why A Workflow Graph

Enterprise agent tasks need resumability, typed state, approval pauses, retries,
and audit. A plain ReAct loop is too implicit for security workflows.

LangGraph should be introduced after the MVP node contracts are clear. The
first step is to model the graph in local types and tests, then wire LangGraph
as the orchestration runtime.

## MVP Graph

Nodes:
- `classify_request`
- `collect_repo_context`
- `retrieve_policy_and_code`
- `analyze_security_risk`
- `plan_actions`
- `propose_report_or_patch`
- `validate`
- `approval_gate`
- `finalize`

Conditional edges:
- missing evidence -> retrieve again or ask clarification
- high-risk action -> approval gate
- malformed model output -> retry with schema error
- validation failure -> repair or report blocker
- user rejection -> revise plan or finalize rejected
- low-risk report-only path -> finalize

## State Fields

- request and normalized task type
- actor and permission snapshot
- repo and branch metadata
- retrieval citations and selected files
- security findings and risk tier
- planned actions
- pending approvals
- patch/report proposal
- validation results
- trace ids and audit event ids
- final outcome

## Human-In-The-Loop

Human interrupts should be required for:
- applying file writes
- running high-risk or policy-sensitive commands
- creating branches, pushing branches, or opening PRs
- executing scanner jobs that use network or proprietary code
- changing config or policy
- using production-like credentials, endpoints, or environments

Approval decisions should support:
- approve
- reject
- request more evidence
- edit plan constraints
- approve only a subset of actions

## Retry And Failure Rules

- Retry schema-invalid model outputs once with validation feedback.
- Do not retry blocked policy actions automatically.
- Do not re-use consumed approvals.
- Do not proceed from failed validation to PR creation without explicit human
  acceptance.
- Preserve partial state for debugging and resume.

## Role Agents

Use roles sparingly:
- `SecurityAnalyzer`: classifies risk and maps evidence to vulnerability types.
- `PolicyReviewer`: checks company policy, compliance, and approval tier.
- `CodeFixer`: proposes minimal code changes.
- `Validator`: selects and interprets tests/scanners.
- `Reporter`: writes the final report with citations and audit references.

Each role must have a typed output schema. Role names alone do not justify a
multi-agent architecture.
