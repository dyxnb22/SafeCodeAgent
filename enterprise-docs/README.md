# Enterprise Technical Docs

**Implementation status (v2.0 RC + post-RC plan):** v1.0–v2.0 are
implemented and contract-frozen; v2.1–v3.0 are planned in
`platform-architecture-v2.md`. See `.agents/context/progress.json` for
live delivery state.
This directory contains the technical context that future Enterprise development
should read first.

Foundation (high-signal context, kept short on purpose):

- `architecture.md` — target system shape (overview).
- `legacy-assets.md` — reusable SafeCodeAgent components and invariants.
- `rag-and-context.md` — retrieval and context packing design.
- `langgraph-workflows.md` — stateful workflow orchestration design.
- `mcp-and-tools.md` — enterprise tool integration design.
- `security-governance.md` — safety, approval, RBAC, and audit rules.
- `observability-and-evaluation.md` — traces, dashboards, and evals.

Detailed technical plans (new, implementation-ready):

- `system-architecture-v1.md` — layered target architecture with mermaid
  diagrams, control flow, trust boundaries, and reuse map. Authoritative
  through `v2.0`.
- `data-models.md` — Pydantic-shaped data model designs for run state,
  citations, findings, approvals, audit, eval, and policy.
- `workflow-design.md` — node graphs, conditional edges, HITL points,
  retries, and demos for the four enterprise workflows
  (PR review, vulnerability remediation, secure implementation
  planning, compliance evidence export).
- `rag-implementation-plan.md` — concrete RAG steps for `v1.1.1`–
  `v1.1.4`, anchored on the existing `context`/`index`/`memory`/`eval`
  primitives.
- `security-governance-plan.md` — policy precedence, RBAC, approval
  engine, and the normative action matrix.
- `evaluation-plan.md` — eval suites, case schema, baselines, ratchets,
  dashboards, and CI wiring.
- `agentops-observability-plan.md` — trace event schema, timeline JSON,
  Markdown dashboard, redaction profiles, and evidence export.
- `deployment-profiles.md` — local, team server, and on-prem hybrid
  deployment shapes (v2.0 RC + post-RC v2.1 upgrade).
- `security-review-v2-0.md` — external-style RC security review notes.
- `platform-architecture-v2.md` — post-RC target architecture for v2.1
  through v3.0 (service / workflow / data / integration / governance /
  observability planes; mermaid diagrams; trust boundaries; migration
  strategy). **Status: planned.**

The goal is clean, useful context. Historical version notes and old product
manuals should stay out of this branch unless they are deliberately distilled
into these files.
