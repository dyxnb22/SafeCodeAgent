---
name: Version 1.6.0 Complete
description: >
  v1.6.0 captures v1.6.0. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 1.6.0 - v1.6.0 snapshot

## Status
Implemented and tagged as `v1.6.0` at `9175373`.

## Base Version
- Depends on: `v1.5.24`
- Stage: `v1.6.x: Controlled Tooling and Subagents`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v1.6.0` implements the `v1.6.0` milestone from `v1.6.x: Controlled Tooling and Subagents`.

- Historical branch: `v1.6.0-mcp-runner-readonly`
- Main entry: `src/safecode/mcp/runner.py`、`src/safecode/cli.py::mcp_call_readonly`

## Main Files
- `src/safecode/mcp/runner.py`
- `src/safecode/cli.py::mcp_call_readonly`

## Acceptance Commands
- MCP 只读工具调用有 audit/runtime log；写工具、network disabled、过大输出被阻止

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
