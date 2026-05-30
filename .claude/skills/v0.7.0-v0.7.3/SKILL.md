---
name: Version 0.7.0-v0.7.3 Complete
description: >
  v0.7.0-v0.7.3 covers v0.7.0 through v0.7.3. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 0.7.0-v0.7.3 - v0.7.0-v0.7.3 snapshot

## Status
Implemented and tagged as `v0.7.0-v0.7.3` at `9c0a047`.

## Base Version
- Depends on: `v0.6.0-v0.6.3`
- Stage: `v0.7.x: Sandbox / Containment`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v0.7.0-v0.7.3` is a range tag for these implemented milestones:

- `v0.7.0`: branch `v0.7.0-sandbox-policy`, entry `src/safecode/config.py::SandboxPolicy`.
- `v0.7.1`: branch `v0.7.1-filesystem-boundary`, entry `src/safecode/sandbox/filesystem.py`.
- `v0.7.2`: branch `v0.7.2-network-policy`, entry `src/safecode/sandbox/network.py`.
- `v0.7.3`: branch `v0.7.3-sandboxed-runner`, entry `src/safecode/shell/runner.py`.

## Main Files
- `src/safecode/config.py::SandboxPolicy`
- `src/safecode/sandbox/filesystem.py`
- `src/safecode/sandbox/network.py`
- `src/safecode/shell/runner.py`

## Acceptance Commands
- `uv run sac config show`
- `PYTHONPATH=src python3 -m pytest tests/test_runtime_extensions.py -q`
- 默认网络策略拒绝外部访问
- `uv run sac run "git status" --yes`

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
