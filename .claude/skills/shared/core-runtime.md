# SafeCodeAgent Enterprise Runtime Summary

The current codebase is still the SafeCodeAgent local runtime. Enterprise
features should extend it without weakening its safety kernel.

Core runtime areas:
- `src/safecode/agent/`: agent loop, approvals, native tools, journals, and
  orchestration.
- `src/safecode/context/` and `src/safecode/index/`: budgeted context,
  redaction, hybrid retrieval hooks, chunking, embeddings, and symbols.
- `src/safecode/mcp/`: MCP discovery, transport, schemas, proposals, and
  approval grants.
- `src/safecode/audit/`: hash-chain audit log and anchors.
- `src/safecode/checkpoint/`: checkpoint and rollback.
- `src/safecode/sandbox/`: sandbox lifecycle and execution gates.
- `src/safecode/llm/`: provider clients, retries, streaming, cost, and
  structured output validation.
- `src/safecode/eval/`: deterministic and live evaluation harnesses.

Enterprise work should introduce typed workflow state, retrieval citations,
policy/RBAC snapshots, approval records, validation records, and run timelines.
