# Reusable Legacy Assets

The original SafeCodeAgent product is finished. Its best long-term value is the
set of safety and runtime primitives that can become the Enterprise platform
kernel.

## Safety Kernel

- Model output is never trusted as execution authority.
- File writes are represented as proposals before application.
- Every write path must pass policy and approval gates.
- Checkpoints are created before mutation.
- Rollback must remain available after writes.
- Audit events form a hash chain with anchors outside the project root.
- Secret redaction is applied before context is sent to models or stored in
  transcripts.

## Agent Runtime Assets

- Conversational shell and agent loop primitives.
- Native read, search, write, command, GitHub, and web fetch tool modules.
- Approval tiers and pending-action models.
- Agent journals and session state.
- Repair and validation retry paths for malformed or failed outputs.

## Context And Memory Assets

- Context budget packer with explicit byte and token budgets.
- Hybrid retrieval hooks that combine keyword, git recency, semantic search,
  and pinned files.
- Redacted session summaries and approved project facts.
- Memory approval rule: pending facts are not injected until approved.
- Explainable context selection via selection reasons.

## Provider Assets

- Mock provider for deterministic tests.
- OpenAI-compatible, Anthropic, and DeepSeek provider clients.
- Structured output validation with recoverable contract failures.
- Bounded retry with jitter and typed rate-limit errors.
- Cost accounting per session.
- Network policy gate before provider calls.
- Fan-out fallback that fails closed and never logs prompt content.

## MCP And Tool Assets

- MCP discovery, stdio transport, schema handling, and read-only runner.
- Static tool classification independent of server-provided JSON fields.
- MCP write proposal and single-use approval grants.
- Output size limits and redaction.
- Native tool specs with approval flags and audit event types.

## Sandbox And Command Assets

- Sandbox lifecycle: propose, preflight, approve, claim, execute, record.
- Approval state stored outside project root and consumed atomically.
- Docker, macOS Seatbelt, and Linux Bubblewrap backends behind explicit gates.
- Default no-network posture.
- `shell=False` subprocess execution.
- High-risk command classification and policy blocks.

## Evaluation Assets

- Local deterministic pytest suite.
- Live-provider eval lane gated by environment variables.
- Ratchet baselines for fixtures that should not regress.
- Redacted transcript artifacts.
- Dashboard output for eval summaries.
- Safety metrics: audit chain complete, checkpoint integrity, unauthorized
  mutations, and clean working tree.

## What Not To Carry Forward

- Version-note archaeology.
- Old tutorial flows that describe finished terminal-only behavior.
- Release train bookkeeping.
- Claims about features that are not part of the Enterprise branch.
- Any prompt-only safety claim without structural enforcement.
