---
name: Version 1.5.0 Complete
description: >
  v1.5.0 captures v1.5.0. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 1.5.0 - v1.5.0 snapshot

## Status
Implemented and tagged as `v1.5.0` at `b0066cf`.

## Base Version
- Depends on: `v1.4.0`
- Stage: `v1.5.x: Core Security Boundary`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v1.5.0` implements the `v1.5.0` milestone from `v1.5.x: Core Security Boundary`.

- Historical branch: `v1.5.0-context-containment`
- Main entry: `src/safecode/context/collector.py`、`src/safecode/sandbox/filesystem.py`

## Main Files
- `src/safecode/context/collector.py`
- `src/safecode/sandbox/filesystem.py`

## Acceptance Commands
- symlink escape / secret content 不进入 context

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
