---
name: Version 1.7.9 Complete
description: >
  v1.7.9 is the current implemented OS-level sandbox containment state.
  Reference this before implementing the next SafeCode Agent version.
---

# Version 1.7.9 - Sandbox Execution Preflight Evals

## Status
Implemented and tagged as `v1.7.9`.

## Base Version
- Depends on: `v1.7.8`
- Stage: `v1.7.x` OS-Level Sandbox Containment
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v1.7.9` adds and validates sandbox execution preflight security evaluations.

The version closes the `v1.7.x` sandbox execution gate by testing the integrity, approval, command, network, filesystem, backend, audit, and CLI preflight boundaries.

## Main Files
- `src/safecode/sandbox/preflight.py`
- `src/safecode/cli.py::sandbox_preflight`
- `tests/test_sandbox_preflight_security_evals.py`

## Acceptance Command
```bash
PYTHONPATH=src python3 -m pytest tests/test_sandbox_preflight_security_evals.py -q
```

## Regression Command
```bash
PYTHONPATH=src python3 -m pytest -q
```

## Backward Compatibility Requirements
- Keep sandbox execution disabled unless the execution gate, approval state, policy, and preflight checks all allow it.
- Preserve existing `sac sandbox plan`, `propose`, `pending`, `discard`, `execute`, `approve`, `approvals`, `revoke`, and `preflight` command behavior.
- Do not weaken command policy, filesystem containment, network deny-by-default, audit logging, or approval binding.

## Notes For Next Version
- Treat `v1.7.9` as the latest sandbox-containment baseline.
- New versions should build on the preflight gate instead of bypassing it.
- If a later version introduces real sandbox execution, require backend-specific tests and keep dry-run/plan behavior available.
