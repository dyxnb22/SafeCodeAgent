---
name: Version 0.6.0-v0.6.3 Complete
description: >
  v0.6.0-v0.6.3 covers v0.6.0 through v0.6.3. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 0.6.0-v0.6.3 - v0.6.0-v0.6.3 snapshot

## Status
Implemented and tagged as `v0.6.0-v0.6.3` at `e08f8e3`.

## Base Version
- Depends on: `v0.5.0-v0.5.3`
- Stage: `v0.6.x: MCP Integration`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v0.6.0-v0.6.3` is a range tag for these implemented milestones:

- `v0.6.0`: branch `v0.6.0-mcp-config`, entry `src/safecode/mcp/config.py`.
- `v0.6.1`: branch `v0.6.1-mcp-tool-discovery`, entry `src/safecode/mcp/discovery.py`.
- `v0.6.2`: branch `v0.6.2-mcp-audit-permission`, entry `src/safecode/audit/models.py`.
- `v0.6.3`: branch `v0.6.3-mcp-demo-tool`, entry `src/safecode/mcp/discovery.py`.

## Main Files
- `src/safecode/mcp/config.py`
- `src/safecode/mcp/discovery.py`
- `src/safecode/audit/models.py`
- `src/safecode/mcp/discovery.py`

## Acceptance Commands
- `.sac/mcp.toml`
- `uv run sac mcp tools`
- 外部工具写操作未来统一走 audit
- 当前提供只读 discovery placeholder

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
