---
name: Current SafeCode Agent Baseline
description: >
  Current implemented SafeCode Agent baseline. Read this with the shared
  runtime summary before implementing the next version.
---

# Current Baseline - v1.9.5

## Status
Implemented locally; tag pending.

## Stage
`v1.9.x` Interactive Agent Loop.

## Source Of Truth
- Version index: `docs/version_implementation_matrix.md`
- Release roadmap: `docs/release_roadmap_v0_1_to_v1_0.md`
- Git baseline: tag `v1.9.3`
- Runtime invariants: `.claude/skills/shared/core-runtime.md`

## Current Capability
SafeCode Agent has a safety-first local runtime centered on controlled file edits, command policy, audit, rollback, and sandbox planning.

The current baseline extends `v1.9.4` by adding agent session recovery commands: `sac agent resume`, `sac agent abort`, and `sac agent explain-last-failure`. Sessions can now be marked aborted with a reason, resumed when not completed, and queried for the latest recorded failure. Standardized human checkpoints remain in place for approval-gated actions, and the typed tool intent router still marks write/execute categories approval-required while malformed intents fail closed. `sac agent run "goal" --max-steps N` remains bounded and stops on completion, max-step exhaustion, or future approval stops. All v1.8.x sandbox safety invariants remain in force.

## Important Entry Points
- `src/safecode/cli.py`
- `src/safecode/agent/approvals.py`
- `src/safecode/agent/loop.py`
- `src/safecode/agent/session.py`
- `src/safecode/agent/tools.py`
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
uv run sac --help
```

## Compatibility Requirements
- Keep sandbox execution disabled unless proposal, approval, policy, and preflight checks all allow it.
- Preserve diff review, checkpoint, audit, rollback, command policy, filesystem containment, network deny-by-default, and approval binding.
- Project-local configuration must not weaken user-level safety policy.
- Only Noop adapter supports real execution. macOS/Linux/Docker adapters must remain dry-run only.
- New historical details belong in docs and Git tags, not in additional `.claude/skills/v*` files.
