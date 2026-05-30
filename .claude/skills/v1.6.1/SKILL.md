---
name: Version 1.6.1 Complete
description: >
  v1.6.1 captures v1.6.1. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 1.6.1 - v1.6.1 snapshot

## Status
Implemented and tagged as `v1.6.1` at `7f1332a`.

## Base Version
- Depends on: `v1.6.0`
- Stage: `v1.6.x: Controlled Tooling and Subagents`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v1.6.1` implements the `v1.6.1` milestone from `v1.6.x: Controlled Tooling and Subagents`.

- Historical branch: `v1.6.1-mcp-write-proposal-only`
- Main entry: `src/safecode/mcp/proposal.py`、`src/safecode/mcp/runner.py::propose_write`、`src/safecode/cli.py::mcp_propose_write`

## Main Files
- `src/safecode/mcp/proposal.py`
- `src/safecode/mcp/runner.py::propose_write`
- `src/safecode/cli.py::mcp_propose_write`

## Acceptance Commands
- `.sac/pending_mcp_call.json`
- `sac mcp propose-write`
- `sac mcp pending`
- `sac mcp discard`

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
