---
name: Current SafeCode Agent Baseline
description: >
  Current implemented SafeCode Agent baseline. Read this with the shared
  runtime summary before implementing the next version.
---

# Current Baseline - v1.8.0

## Status
Implemented and tagged as `v1.8.0`.

## Stage
`v1.8.x` Local Policy-Gated Sandbox Execution.

## Source Of Truth
- Version index: `docs/version_implementation_matrix.md`
- Release roadmap: `docs/release_roadmap_v0_1_to_v1_0.md`
- Git baseline: tag `v1.8.0`
- Runtime invariants: `.claude/skills/shared/core-runtime.md`

## Current Capability
SafeCode Agent has a safety-first local runtime centered on controlled file edits, command policy, audit, rollback, and sandbox planning.

The current baseline extends `v1.7.9` by enabling real sandbox execution through the **Noop adapter** (local policy-gated execution). Commands run via SafeCode's own `ShellRunner` (CommandPolicy + NetworkPolicy + FilesystemBoundary) when all preflight checks pass (proposal integrity, approval, command policy, network policy, filesystem boundary, backend capability). macOS Seatbelt, Linux Bubblewrap, and Docker adapters remain dry-run only. No OS sandbox binary is ever invoked.

## Important Entry Points
- `src/safecode/cli.py`
- `src/safecode/sandbox/execution.py`
- `src/safecode/sandbox/preflight.py`
- `src/safecode/sandbox/adapter.py`
- `src/safecode/sandbox/`
- `src/safecode/policy/commands.py`
- `src/safecode/shell/`
- `src/safecode/audit/`
- `tests/test_sandbox_execution_security_evals.py`

## Verification
```bash
PYTHONPATH=src python3 -m pytest tests/test_sandbox_execution_security_evals.py -q
PYTHONPATH=src python3 -m pytest -q
```

## Compatibility Requirements
- Keep sandbox execution disabled unless proposal, approval, policy, and preflight checks all allow it.
- Preserve diff review, checkpoint, audit, rollback, command policy, filesystem containment, network deny-by-default, and approval binding.
- Project-local configuration must not weaken user-level safety policy.
- Only Noop adapter supports real execution. macOS/Linux/Docker adapters must remain dry-run only.
- New historical details belong in docs and Git tags, not in additional `.claude/skills/v*` files.
