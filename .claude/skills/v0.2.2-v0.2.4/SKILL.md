---
name: Version 0.2.2-v0.2.4 Complete
description: >
  v0.2.2-v0.2.4 covers v0.2.2 through v0.2.4. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 0.2.2-v0.2.4 - v0.2.2-v0.2.4 snapshot

## Status
Implemented and tagged as `v0.2.2-v0.2.4` at `df29f96`.

## Base Version
- Depends on: `v0.2.1`
- Stage: `v0.2.x: Permissioned Shell Runtime`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v0.2.2-v0.2.4` is a range tag for these implemented milestones:

- `v0.2.2`: branch `v0.2.2-sac-run-readonly`, entry `src/safecode/shell/runner.py`.
- `v0.2.3`: branch `v0.2.3-sac-run-approval`, entry `src/safecode/cli.py::run_command`.
- `v0.2.4`: branch `v0.2.4-shell-audit-history`, entry `src/safecode/audit/models.py`.

## Main Files
- `src/safecode/shell/runner.py`
- `src/safecode/cli.py::run_command`
- `src/safecode/audit/models.py`

## Acceptance Commands
- `uv run sac run "git status --short" --yes`
- `uv run sac run "rm -rf /tmp/example"`
- `uv run sac history`

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
