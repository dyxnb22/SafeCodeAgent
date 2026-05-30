---
name: Version 1.4.0 Complete
description: >
  v1.4.0 captures v1.4.0. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 1.4.0 - v1.4.0 snapshot

## Status
Implemented and tagged as `v1.4.0` at `40d12d0`.

## Base Version
- Depends on: `v1.3.4`
- Stage: `v1.4.x: Runtime Operations`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v1.4.0` implements the `v1.4.0` milestone from `v1.4.x: Runtime Operations`.

- Historical branch: `v1.4.0-runtime-logging`
- Main entry: `src/safecode/logs/runtime.py`、`src/safecode/cli.py`

## Main Files
- `src/safecode/logs/runtime.py`
- `src/safecode/cli.py`

## Acceptance Commands
- `uv run sac logs show --level error --traceback`

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
