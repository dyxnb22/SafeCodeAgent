# Agent Context

This branch is for SafeCodeAgent Enterprise: a new enterprise security
engineering agent platform built from the finished SafeCodeAgent foundation.

Primary context:
- `product-planning/`
- `enterprise-docs/`
- `src/safecode/`
- `tests/`

Legacy SafeCodeAgent user docs were intentionally removed from this branch after
extraction to reduce noisy context. For the final legacy product docs, inspect
the `archive/safecodeagent-final` branch or `main`.

Do not recreate old version notes or historical roadmaps in this branch. New
documentation should describe Enterprise product behavior, architecture, or
implementation tasks.

Critical invariants to preserve:
- Model output is never execution authority.
- File writes, commands, MCP writes, GitHub writes, and production-like actions
  must pass deterministic policy gates.
- Human approval, checkpoint, rollback, audit, and redaction stay structural.
- Network access and provider endpoints must be explicitly allowed.
- Project-local configuration cannot lower user-level or organization-level
  safety.
- RAG and memory must cite sources, respect permissions, and avoid injecting
  unapproved facts.
