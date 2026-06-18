# SafeCodeAgent Enterprise

This branch evolves the finished SafeCodeAgent safety-first coding agent into an
enterprise security engineering agent platform.

SafeCodeAgent itself is complete and preserved on `main` and
`archive/safecodeagent-final`. This branch is for the next product direction:
RAG-grounded security workflows, LangGraph-style orchestration, MCP/tool
integrations, human approval, policy governance, observability, and evaluation.

## What This Branch Is For

- PR security review with policy and code citations.
- Vulnerability remediation from scanner findings to proposed fixes.
- Secure implementation planning from tickets or requirements.
- Auditable agent runs with tool calls, approvals, validation, cost, and traces.
- Enterprise integration with GitHub, CI, scanners, ticketing, and knowledge
  sources through governed tools and MCP connectors.

## Start Here

- Product direction: `product-planning/README.md`
- Roadmap: `product-planning/roadmap.md`
- Implementation backlog: `product-planning/implementation-backlog.md`
- Technical architecture: `enterprise-docs/architecture.md`
- Reusable SafeCodeAgent assets: `enterprise-docs/legacy-assets.md`
- RAG design: `enterprise-docs/rag-and-context.md`
- LangGraph workflow design: `enterprise-docs/langgraph-workflows.md`
- Tool and MCP design: `enterprise-docs/mcp-and-tools.md`
- Security governance: `enterprise-docs/security-governance.md`
- Observability and evaluation: `enterprise-docs/observability-and-evaluation.md`

## Legacy Docs

The legacy SafeCodeAgent docs were intentionally removed from this branch after
extracting useful Enterprise development context. This keeps agent and IDE
context focused and avoids spending tokens on completed-product history.

For old SafeCodeAgent docs, inspect:

- `main`
- `archive/safecodeagent-final`

## Development

```bash
uv sync
uv run sac --help
PYTHONPATH=src python3 -m pytest -q
```

Critical invariant: model output is never execution authority. Writes, command
execution, MCP writes, GitHub writes, sandbox execution, network actions, and
approval-sensitive operations must stay policy-gated, auditable, and
recoverable.
