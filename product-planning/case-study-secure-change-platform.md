# Secure-Change Platform Case Study

This case study walks through one offline PR security review on the
SafeCodeAgent Enterprise platform. It is written for a 15-minute interview
walkthrough. It describes implemented behavior in this repository; it does
**not** claim enterprise GA approval or close external GA gates G1/G2/G3.

**Status:** `v3.0` candidate blocked on external evidence; portfolio track
documentation only.

**Demo fixture:** `examples/enterprise/fixtures/pr_sql_injection/pr.json`

**Offline command:** `uv run sac demo pr-review --offline`

---

## Scenario

A pull request adds a Python helper that builds SQL with string
interpolation. The platform must:

1. Classify the request as PR security review.
2. Collect PR evidence from an offline fixture (no live GitHub).
3. Retrieve policy and code citations with permission scope.
4. Analyze risk and plan governed actions.
5. Propose a report (model output remains a proposal).
6. Pause at the approval gate for high-risk writes.
7. Record trace events and append-only audit evidence.

The portfolio demo rejects the approval request to show that execution
authority stays with policy and humans, not the model.

---

## End-to-End Flow

```text
PR fixture ingest
  → classify_request
  → collect_repo_context
  → retrieve_policy_and_code
  → analyze_security_risk
  → plan_actions
  → propose_report_or_patch
  → validate
  → approval_gate (human decision required)
  → finalize (only after approved grant)
```

Reference workflow design: `enterprise-docs/workflow-design.md`.

---

## RAG

Permission-aware retrieval grounds the review in org policy, code, scanner
baselines, and runbooks. Chunks carry source identity and citation IDs; the
retriever enforces actor scope and tenant boundaries.

**Implementation:** `src/safecode/enterprise/rag/retriever.py` — hybrid
scoring over manifest-backed chunks with stable `citation_id` generation.

**Regression:** `tests/enterprise/rag/test_source_registry.py` — manifest
loading, permission scope, and source registry contracts.

**Interview point:** Retrieval is evidence for workflow nodes, not a chat
answer. Missing or out-of-scope sources mark `missing_evidence` instead of
hallucinating policy.

---

## Workflow / Agent Orchestration

The local orchestrator runs nine typed nodes in deterministic order, persists
checkpoints under `.sac/enterprise/runs/`, and raises `WorkflowInterrupted`
when human approval is required. Resume replays from the saved checkpoint.

**Implementation:** `src/safecode/enterprise/workflow/orchestrator.py` —
`LocalOrchestrator.run()` / `resume()` with node registry and trace emission.

**Regression:** `tests/enterprise/workflow/test_orchestrator_happy_path.py`
— nine-node order, checkpoint persistence, succeeded terminal state.

**Interview point:** This is a state machine with resumable checkpoints, not
a free-form agent loop. Model output never becomes execution authority.

---

## MCP / Tool Calling

Enterprise connectors wrap GitHub, Jira, scanners, and MCP capabilities behind
local classification and governance checks. MCP server-claimed metadata is not
trusted for authorization decisions.

**Implementation:** `src/safecode/enterprise/connectors/mcp_adapter.py` —
allowlisted MCP tool registration with local category and action mapping.

**Regression:**
`tests/enterprise/connectors/test_mcp_server_classification_ignored.py` —
server-supplied labels cannot bypass local deny-by-default classification.

**Interview point:** Tools are typed contracts evaluated by policy and RBAC;
MCP is an integration surface, not a security boundary by itself.

---

## Guardrails / Policy

Policy precedence resolves org, project, and runtime snapshots. Writes,
commands, connector operations, and debug trace export require explicit
allow rules; unknown actions default to denied.

**Implementation:** `src/safecode/enterprise/policy/resolver.py` — layered
snapshot resolution with no-weakening semantics toward user/org policy.

**Regression:** `tests/enterprise/policy/test_resolver_precedence.py` —
higher-precedence policy wins; project-local config cannot weaken org rules.

**Interview point:** Guardrails are structural gates on action categories,
not prompt suggestions.

---

## Human-in-the-Loop

High-risk PR review proposals bind to a single-use approval request. The
workflow interrupts until a human approver decides; rejected requests
terminate without finalize-side effects.

**Implementation:** `src/safecode/enterprise/approvals/store.py` — request,
grant, and decision persistence with consumption tracking.

**Regression:** `tests/enterprise/workflow/test_approval_interrupt.py` —
interrupt persists pending request; approve/resume completes; reject stays
terminal.

**Interview point:** Approvals are scoped, auditable, and bound to the exact
proposal snapshot; agents cannot self-approve.

---

## Observability / Trace

Each node emits redacted trace events assembled into a run timeline suitable
for Markdown export and console views. Strict export profiles redact secrets
and oversized payloads before persistence.

**Implementation:** `src/safecode/enterprise/trace/timeline.py` — canonical
`RunTimeline` construction from trace events.

**Regression:** `tests/enterprise/trace/test_timeline_round_trip.py` —
timeline serialize/deserialize and redaction profile behavior.

**Interview point:** Observability is audit-friendly evidence, not raw model
prompt logging by default.

---

## Evaluation / Regression

Deterministic eval suites exercise retrieval, prompt-injection resistance, tool
classification, PR review, and remediation flows against fixtures. Baseline
ratchets block silent quality regressions.

**Implementation:** `src/safecode/enterprise/eval/runner.py` — suite
discovery and case execution without live providers.

**Regression:** `tests/enterprise/eval/test_runner_round_trip.py` — case
loading, execution, and structured pass/fail recording.

**Interview point:** Evaluation is offline-first; live-provider lanes are
optional and never substitute for external GA evidence.

---

## Audit / Evidence

Enterprise audit events append to the legacy hash-chain logger with run and
tenant metadata. Evidence export bundles checkpoint, timeline, and chain
verification for compliance review.

**Implementation:** `src/safecode/enterprise/audit/chain.py` — enterprise
taxonomy wrapper over `AuditLogger` with integrity verification.

**Regression:** `tests/enterprise/eval/cases/pr_review/sql_injection.yaml`
— PR review fixture case expects `audit_chain_intact` alongside workflow
assertions.

**Interview point:** Audit is append-only and hash-chained; export is a
read-only compliance artifact, not a write path.

---

## What To Show In Fifteen Minutes

1. Run `uv run sac demo pr-review --offline` and open
   `examples/enterprise/demos/v3.2/transcripts/pr-review.txt`.
2. Open `src/safecode/enterprise/workflow/orchestrator.py` and map demo node
   names to code.
3. Open `src/safecode/enterprise/rag/retriever.py` and explain citation IDs
   in the demo output.
4. Open `tests/enterprise/workflow/test_approval_interrupt.py` and explain
   why reject is terminal.
5. Open `enterprise-docs/security/external-gates.md` and state clearly that
   portfolio readiness does not close enterprise GA.

---

## Honest Status Boundaries

- **Implemented:** offline PR review workflow, governance, trace, eval, and
  audit paths cited above.
- **Candidate / pending:** independent security reviewer signature,
  production-like deployment evidence, stable live-provider workflow evidence.
- **Portfolio final:** presentation and reproducibility; not enterprise GA.

See `product-planning/post-ga-portfolio-roadmap.md` and
`.agents/context/progress.json` for live track state.
