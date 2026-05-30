---
name: Version 1.1.0-v1.1.5 Complete
description: >
  v1.1.0-v1.1.5 covers v1.1.0 through v1.1.5. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 1.1.0-v1.1.5 - v1.1.0-v1.1.5 snapshot

## Status
Implemented and tagged as `v1.1.0-v1.1.5` at `a27b9b0`.

## Base Version
- Depends on: `v1.0.0-v1.0.5`
- Stage: `v1.1.x: Product Extension Layer`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v1.1.0-v1.1.5` is a range tag for these implemented milestones:

- `v1.1.0`: branch `v1.1.0-local-api-facade`, entry `src/safecode/api.py`.
- `v1.1.1`: branch `v1.1.1-export-reports`, entry `src/safecode/export/bundle.py`.
- `v1.1.2`: branch `v1.1.2-local-task-queue`, entry `src/safecode/queue/store.py`.
- `v1.1.3`: branch `v1.1.3-ide-manifest`, entry `src/safecode/ide/manifest.py`.
- `v1.1.4`: branch `v1.1.4-release-checklist`, entry `src/safecode/release/checklist.py`.
- `v1.1.5`: branch `v1.1.5-extension-polish`, entry `全部扩展层`.

## Main Files
- `src/safecode/api.py`
- `src/safecode/export/bundle.py`
- `src/safecode/queue/store.py`
- `src/safecode/ide/manifest.py`
- `src/safecode/release/checklist.py`
- 全部扩展层

## Acceptance Commands
- `SafeCodeLocalAPI(Path.cwd()).ask(...)`
- `uv run sac export report`
- `uv run sac queue add "demo"`
- `uv run sac ide manifest --write`
- `uv run sac release checklist v1.1.4`
- `PYTHONPATH=src python3 -m pytest -q`

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
