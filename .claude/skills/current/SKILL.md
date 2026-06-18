---
name: SafeCodeAgent Enterprise Baseline
description: >
  Current branch context for evolving SafeCodeAgent into an enterprise security
  engineering agent platform.
---

# SafeCodeAgent Enterprise Baseline

This branch starts from the completed SafeCodeAgent safety-first coding agent
and redirects development toward Enterprise workflows.

Implemented. Git baseline: tag `v7.1.5`.

## Product Goal

Build a governed agent platform for:
- PR security review
- vulnerability remediation
- secure implementation planning
- compliance evidence
- auditable tool-using security workflows

## Reusable Kernel

Keep these SafeCodeAgent primitives:
- policy-gated file writes
- checkpoint and rollback
- hash-chain audit logs
- native read/write/command tools
- MCP proposal and approval flow
- sandbox proposal/preflight/approval/execution lifecycle
- redacted memory and approved facts
- context budget and hybrid retrieval hooks
- provider clients with structured output validation
- eval fixtures, live smoke, and dashboard artifacts

## New Enterprise Direction

Planned layers:
- permission-aware RAG over code, policy, docs, historical fixes, and findings
- LangGraph-compatible workflow state and human interrupts
- role agents with typed outputs
- MCP/native tool governance
- RBAC, organization policy, and approval tiers
- trace, cost, retrieval, approval, and validation observability
- enterprise eval suites for security workflows

## Current Source Of Truth

- `product-planning/README.md`
- `product-planning/roadmap.md`
- `product-planning/implementation-backlog.md`
- `enterprise-docs/README.md`
- `enterprise-docs/legacy-assets.md`
- `enterprise-docs/architecture.md`
- `enterprise-docs/rag-and-context.md`
- `enterprise-docs/langgraph-workflows.md`
- `enterprise-docs/mcp-and-tools.md`
- `enterprise-docs/security-governance.md`
- `enterprise-docs/observability-and-evaluation.md`

Do not use old version notes as active planning. Legacy docs are available on
`main` and `archive/safecodeagent-final`.
