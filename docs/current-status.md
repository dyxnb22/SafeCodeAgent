# SafeCode Current Status

**Current documented baseline:** `v7.1.5`  
**Stable contract cut:** `v7.0.0`  
**Package/runtime metadata:** `7.1.5`

SafeCode Agent is a safety-first terminal coding agent. Its core product shape is
stable: collect project context, propose or run bounded coding steps, gate every
write through policy and approval, checkpoint files before mutation, and keep a
hash-chain audit trail for later inspection and rollback.

## Current Product Shape

- Terminal-first `sac` workflow with no IDE or desktop runtime dependency.
- Policy-gated file writes, command execution, MCP write tools, and trust modes.
- SHA-256 checkpoints plus rollback for applied edits.
- Hash-chain audit logs for tamper-evident local history.
- Multi-provider model configuration, provider diagnostics, and live smoke paths.
- Agentic shell and `sac agent run` flows that keep mutating steps approval-gated.
- Native read/write/search tools, workspace memory, semantic search hooks, and
  subagent role support.
- Live evaluation harness with coding fixtures, ratchet baseline, and Markdown
  dashboard output.

## Stable Guarantees

The current stable public surface is tracked in
[public-contracts.md](public-contracts.md). The v7 contract baseline keeps the
v6 safety guarantees and productizes the agent workflow without adding hidden
auto-write behavior:

- Writes are not executed solely because a model asked for them.
- Approval tiers decide whether a step is automatic, confirmable, or gated.
- Rollback and audit records remain part of the write path.
- Trust modes reduce prompts but do not bypass GATE-tier stops.
- Release metadata, changelog, and docs checks use
  [release-ledger.md](release-ledger.md) as the compact current history.

## Experimental Or Evolving Areas

- Web/GitHub workflow helpers remain guarded by approval policy and local CLI
  availability.
- Semantic retrieval depends on optional extras and degrades to explicit guidance
  when inactive.
- Evaluation dashboards are useful for release confidence, but fixture scope and
  provider behavior should still be reviewed before making product claims.

## Evidence To Read

- First-run workflow: [user-guide.md](user-guide.md)
- Command surface: [reference/commands.md](reference/commands.md)
- Version map: [reference/version-summary.md](reference/version-summary.md)
- Compact release history: [release-ledger.md](release-ledger.md)
- Detailed implementation archaeology:
  [version_implementation_matrix.md](version_implementation_matrix.md)
- Demo evidence: [demo/portfolio-demo.md](demo/portfolio-demo.md) and
  [evaluation.md](evaluation.md)

## Forward Planning

No active version plan is currently open. Start new version-specific work from
[version-plans/_template.md](version-plans/_template.md), then record completed
work in [release-ledger.md](release-ledger.md). Completed planning records are
summarized in [planning-history.md](planning-history.md).
