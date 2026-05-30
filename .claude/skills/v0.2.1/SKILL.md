---
name: Version 0.2.1 Complete
description: >
  v0.2.1 captures v0.2.1. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 0.2.1 - v0.2.1 snapshot

## Status
Implemented and tagged as `v0.2.1` at `c82b591`.

## Base Version
- Depends on: `v0.2.0`
- Stage: `v0.2.x: Permissioned Shell Runtime`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v0.2.1` implements the `v0.2.1` milestone from `v0.2.x: Permissioned Shell Runtime`.

- Historical branch: `v0.2.1-shell-risk-classifier`
- Main entry: `src/safecode/shell/risk.py`

## Main Files
- `src/safecode/shell/risk.py`

## Acceptance Commands
- `PYTHONPATH=src python3 -m pytest tests/test_runtime_extensions.py -q`

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
