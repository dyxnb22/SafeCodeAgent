# Enterprise Technical Docs

**Implementation status (v3.0 candidate + portfolio track):** v1.0–v2.5 are
implemented; v3.0 is a candidate blocked on external GA gates; portfolio
`v3.1`–`v3.4` presentation track is complete. See `.agents/context/progress.json`
and `../docs/architecture-poster.md` for live delivery state.
This directory contains the technical context that future Enterprise development
should read first.

Foundation (high-signal context, kept short on purpose; background only):

- `architecture.md` — target system shape (overview, foundation).
- `legacy-assets.md` — reusable SafeCodeAgent components and invariants.
- `rag-and-context.md` — retrieval and context packing design (foundation).
- `langgraph-workflows.md` — stateful workflow orchestration design (foundation).
- `mcp-and-tools.md` — enterprise tool integration design (foundation).
- `security-governance.md` — safety, approval, RBAC, and audit rules (foundation).
- `observability-and-evaluation.md` — traces, dashboards, and evals (foundation).

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
- `security/security-review-v3.0.md` — v3.0 candidate security review (not
  external sign-off).
- `security/external-gates.md` — G1/G2/G3 external GA gates that cannot
  be closed by repository-local agents or fabricated evidence.
- `platform-architecture-v2.md` — post-RC target architecture for v2.1
  through v3.0 (service / workflow / data / integration / governance /
  observability planes; mermaid diagrams; trust boundaries; migration
  strategy). **Status: implemented through v2.5; v3.0 candidate.**

The goal is clean, useful context. Historical version notes and old product
manuals should stay out of this branch unless they are deliberately distilled
into these files.
