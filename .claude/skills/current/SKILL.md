---
name: Current SafeCode Agent Baseline
description: >
  Current implemented SafeCode Agent baseline. Read this with the shared
  runtime summary before implementing the next version.
---

# Current Baseline - v1.9.3

## Status
Implemented and tagged as `v1.9.3`.

## Stage
`v1.9.x` Interactive Agent Loop.

## Source Of Truth
- Version index: `docs/version_implementation_matrix.md`
- Release roadmap: `docs/release_roadmap_v0_1_to_v1_0.md`
- Git baseline: tag `v1.9.3`
- Runtime invariants: `.claude/skills/shared/core-runtime.md`

## Current Capability
SafeCode Agent has a safety-first local runtime centered on controlled file edits, command policy, audit, rollback, and sandbox planning.

The current baseline extends `v1.9.2` by adding a typed tool intent router for read, patch, shell, sandbox, MCP, subagent, and report actions. `sac agent step` records a validated read intent with route metadata, while write/execute intent categories are marked approval-required and unknown or malformed intents fail closed. `sac agent run "goal" --max-steps N` remains bounded and stops on completion, max-step exhaustion, or future approval stops. All v1.8.x sandbox safety invariants remain in force: Noop is the only real execution backend, approval claim is single-use and atomic, macOS/Linux/Docker backends remain dry-run, and sandbox execution remains gated by proposal, approval, preflight, command policy, network policy, filesystem boundary, and backend capability.

## Important Entry Points
- `src/safecode/cli.py`
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
