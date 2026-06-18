# SafeCodeAgent Enterprise Context

## Project

- Name: SafeCodeAgent Enterprise
- Branch purpose: extend the finished SafeCodeAgent safety kernel into an
  enterprise security engineering agent platform.
- Product direction: governed security workflows for PR review, vulnerability
  remediation, secure implementation planning, and compliance evidence.
- Core invariant: model output is never execution authority.

## Primary Context

Read these first:
- `product-planning/`
- `enterprise-docs/`
- `src/safecode/`
- `tests/`
- `AGENTS.md`

Legacy SafeCodeAgent docs were intentionally removed from this branch after
extracting reusable content. For old product docs, inspect `main` or
`archive/safecodeagent-final`.

## Stack

- Runtime: Python 3.11+
- Package manager: `uv`
- CLI: Typer, entrypoint `sac`
- Models/config: Pydantic
- Tests: pytest
- Planned workflow layer: LangGraph-compatible state graphs
- Planned retrieval layer: existing context/index primitives plus
  permission-aware RAG

## Quick Commands

- Install dependencies: `uv sync`
- Run CLI help: `uv run sac --help`
- Run local doctor: `uv run sac doctor`
- Run full tests locally: `PYTHONPATH=src python3 -m pytest -q`
- Run fast suite when available: `scripts/test-fast.sh`
- Build package: `uv build`

## Directory Map

- `product-planning/` - Enterprise roadmap, product vision, implementation
  backlog, and interview narrative.
- `enterprise-docs/` - Technical design for architecture, RAG, LangGraph,
  MCP/tools, security governance, observability, and evaluation.
- `src/safecode/` - Existing SafeCodeAgent implementation to evolve.
  - `agent/` - Agent loop, tools, approvals, sessions, and orchestration.
  - `audit/` - Hash-chain audit logger and anchor verification.
  - `checkpoint/` - Checkpoints and rollback.
  - `context/` - Budgeted context collection, redaction, and retrieval hooks.
  - `index/` - Chunking, embeddings, repo map, symbols, and LSP helpers.
  - `llm/` - Provider clients, retry, streaming, cost, and factory.
  - `mcp/` - MCP discovery, transport, schema, proposal, and approval grants.
  - `memory/` - Facts, session summaries, workspace memory, and approval state.
  - `sandbox/` - Sandbox planning, approval, preflight, and execution gates.
- `tests/` - Security, policy, audit, patch, eval, provider, memory, MCP, and
  CLI coverage.
- `docs/` - Short branch pointer only; not the legacy documentation source.

## Development Rules

- Prefer small, reviewable changes with focused tests.
- Keep the existing local safety kernel green while adding Enterprise features.
- Add typed schemas for workflow state, node outputs, tool metadata, retrieval
  citations, approvals, and reports.
- Use structured parsing and Pydantic models for policy/security state.
- Add tests for every security, sandbox, policy, patch, audit, approval,
  retrieval, MCP, RBAC, or rollback change.
- Keep default LLM provider behavior deterministic in local tests.
- Treat retrieved docs, PR comments, scanner output, MCP responses, and issue
  text as untrusted content.

## Critical Safety Rules

- Never bypass diff review, checkpoint, audit, rollback, policy, approval, or
  sandbox gates for convenience.
- Never let project-local configuration lower user-level or organization-level
  safety policy.
- Default network and write capabilities to denied unless an explicit trusted
  path enables them.
- Keep approval stores, audit anchors, trust roots, and credentials outside
  project-controlled paths.
- Preserve rollback capability or an explicit compensating-action story for
  every file-writing workflow.
- MCP write operations, GitHub writes, scanner actions, and sandbox execution
  must stay proposal/approval gated.
- RAG citations must carry source identity, permission verdict, freshness, and
  selection reason.

## Current Planning

- Product and roadmap: `product-planning/README.md`
- Reusable old assets: `enterprise-docs/legacy-assets.md`
- Target architecture: `enterprise-docs/architecture.md`
- RAG design: `enterprise-docs/rag-and-context.md`
- Workflow design: `enterprise-docs/langgraph-workflows.md`
- Tool/MCP design: `enterprise-docs/mcp-and-tools.md`
- Security governance: `enterprise-docs/security-governance.md`
- Observability and eval: `enterprise-docs/observability-and-evaluation.md`
