---
name: Current SafeCode Agent Baseline
description: >
  Current implemented SafeCode Agent baseline. Read this with the shared
  runtime summary before implementing the next version.
---

# Current Baseline - v1.7.9

## Status
Implemented and tagged as `v1.7.9`.

## Stage
`v1.7.x` OS-Level Sandbox Containment.

## Source Of Truth
- Version index: `docs/version_implementation_matrix.md`
- Release roadmap: `docs/release_roadmap_v0_1_to_v1_0.md`
- Git baseline: tag `v1.7.9`
- Runtime invariants: `.claude/skills/shared/core-runtime.md`

## Current Capability
SafeCode Agent has a safety-first local runtime centered on controlled file edits, command policy, audit, rollback, and sandbox planning.

The current baseline closes the `v1.7.x` sandbox execution gate with preflight security evaluations across proposal integrity, approval state, command policy, network policy, filesystem boundaries, backend behavior, audit behavior, and CLI privacy.

## Important Entry Points
- `src/safecode/cli.py`
- `src/safecode/sandbox/preflight.py`
- `src/safecode/sandbox/`
- `src/safecode/policy/commands.py`
- `src/safecode/shell/`
- `src/safecode/audit/`
- `tests/test_sandbox_preflight_security_evals.py`

## Verification
```bash
PYTHONPATH=src python3 -m pytest tests/test_sandbox_preflight_security_evals.py -q
PYTHONPATH=src python3 -m pytest -q
```

## Compatibility Requirements
- Keep sandbox execution disabled unless proposal, approval, policy, and preflight checks all allow it.
- Preserve diff review, checkpoint, audit, rollback, command policy, filesystem containment, network deny-by-default, and approval binding.
- Project-local configuration must not weaken user-level safety policy.
- New historical details belong in docs and Git tags, not in additional `.claude/skills/v*` files.
