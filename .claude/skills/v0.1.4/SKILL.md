---
name: Version 0.1.4 Complete
description: >
  v0.1.4 captures v0.1.4. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 0.1.4 - v0.1.4 snapshot

## Status
Implemented and tagged as `v0.1.4` at `2e05bd1`.

## Base Version
- Depends on: `v0.1.0-v0.1.3`
- Stage: `v0.1.x`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v0.1.4` implements the `v0.1.4` milestone from `v0.1.x`.

- Historical branch: `v0.1.4-rollback-history`
- Main entry: `src/safecode/checkpoint/manager.py`

## Main Files
- `src/safecode/checkpoint/manager.py`

## Acceptance Commands
- `uv run sac rollback --last && uv run sac history`

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
