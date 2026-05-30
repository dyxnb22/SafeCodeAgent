---
name: Version 0.3.0-v0.3.3 Complete
description: >
  v0.3.0-v0.3.3 covers v0.3.0 through v0.3.3. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 0.3.0-v0.3.3 - v0.3.0-v0.3.3 snapshot

## Status
Implemented and tagged as `v0.3.0-v0.3.3` at `f60d643`.

## Base Version
- Depends on: `v0.2.2-v0.2.4`
- Stage: `v0.3.x: Long-running State`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v0.3.0-v0.3.3` is a range tag for these implemented milestones:

- `v0.3.0`: branch `v0.3.0-sac-md-project-rules`, entry `src/safecode/project/rules.py`.
- `v0.3.1`: branch `v0.3.1-progress-file`, entry `src/safecode/state/progress.py`.
- `v0.3.2`: branch `v0.3.2-hooks-after-apply`, entry `src/safecode/hooks/runner.py`.
- `v0.3.3`: branch `v0.3.3-lightweight-memory`, entry `src/safecode/memory/store.py`.

## Main Files
- `src/safecode/project/rules.py`
- `src/safecode/state/progress.py`
- `src/safecode/hooks/runner.py`
- `src/safecode/memory/store.py`

## Acceptance Commands
- `uv run sac rules --init`
- `uv run sac progress set "demo goal" --next "next step"`
- `[hooks].after_apply`
- `uv run sac apply`
- `uv run sac memory test_command "pytest -q"`

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
