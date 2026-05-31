# v2.3.4 Product Review Follow-up

## Decision

Do not move directly from `v2.3.4` into real sandbox backends. The product review found that SafeCode Agent has a strong safety substrate, but the user-facing product surface still overstates or blurs several boundaries:

- Sandbox execution is currently real only through the Noop backend; macOS Seatbelt, Linux Bubblewrap, and Docker are still plan-only/dry-run surfaces.
- MCP support is currently a subprocess JSON shim, not a full MCP JSON-RPC client.
- Subagents are read-only context/result collectors, not independent LLM investigations.
- The interactive `AgentLoop` does not yet produce patches end-to-end.
- Tool registry metadata is not yet the universal gate for every CLI write/execute/tool path.

## Immediate Track

Before enabling real sandbox backends, complete:

1. `v2.3.5-honest-surface`
   - Make CLI output and docs explicit about Noop-only execution, plan-only non-Noop backends, MCP shim semantics, and subagent limitations.
   - Primary files: `src/safecode/cli_sandbox.py`, `src/safecode/cli_mcp.py`, `src/safecode/cli_subagent.py`, docs.

2. `v2.3.6-agent-loop-patch-path`
   - Wire `AgentLoop` into patch proposal generation so `sac agent run "goal"` can create `.sac/pending_patch.json` and stop for approval.
   - Primary files: `src/safecode/agent/loop.py`, `src/safecode/agent/tools.py`, `src/safecode/llm/mock.py`, `src/safecode/patch/`.

3. `v2.3.7-universal-gate-and-migrations`
   - Route all CLI write/execute/tool paths through a universal ToolCallAdapter-based gate.
   - Add schema-versioned migration hooks for persisted session, journal, proposal, approval, and result records.
   - Primary files: `src/safecode/tools/`, `src/safecode/cli_*.py`, `src/safecode/state/migrations.py`.

## Revised v2.4 Order

After stabilization:

1. `v2.4.0-sandbox-backend-contract-v2`
2. `v2.4.1-docker-execution-preview`
3. `v2.4.2-macos-seatbelt-execution-preview`
4. `v2.4.3-linux-bubblewrap-execution-preview`
5. `v2.4.4-cross-backend-security-evals`

Docker moves first because it is the most uniform across macOS, Linux, and CI. Seatbelt and Bubblewrap need more host-specific validation and should follow once the backend execution contract is proven.

## Product Framing

SafeCode Agent should continue positioning itself as a safety-first local runtime for diff-mediated edits, policy-gated commands, auditability, and gradual sandboxing. Near-term product work should make the surface honest and cohesive before expanding enforcement claims.
