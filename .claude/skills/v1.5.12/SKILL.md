---
name: Version 1.5.12 Complete
description: >
  v1.5.12 captures v1.5.12. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 1.5.12 - v1.5.12 snapshot

## Status
Implemented and tagged as `v1.5.12` at `8935f5c`.

## Base Version
- Depends on: `v1.5.11`
- Stage: `v1.5.x: Core Security Boundary`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v1.5.12` implements the `v1.5.12` milestone from `v1.5.x: Core Security Boundary`.

- Historical branch: `v1.5.12-command-policy-bypass-fixes`
- Main entry: `src/safecode/policy/commands.py`

## Main Files
- `src/safecode/policy/commands.py`

## Acceptance Commands
- git pager/editor/diff command、node --eval、python stdin、npx/pip3/pipx/uv pip 被阻止

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
