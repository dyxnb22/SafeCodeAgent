---
name: Current SafeCode Agent Baseline
description: >
  Current implemented SafeCode Agent baseline. Read this with the shared
  runtime summary before implementing the next version.
---

# Current Baseline - v1.8.6

## Status
Implemented and tagged as `v1.8.6`.

## Stage
`v1.8.x` Local Policy-Gated Sandbox Execution.

## Source Of Truth
- Version index: `docs/version_implementation_matrix.md`
- Release roadmap: `docs/release_roadmap_v0_1_to_v1_0.md`
- Git baseline: tag `v1.8.1`
- Runtime invariants: `.claude/skills/shared/core-runtime.md`

## Current Capability
SafeCode Agent has a safety-first local runtime centered on controlled file edits, command policy, audit, rollback, and sandbox planning.

The current baseline extends `v1.7.9` by enabling real sandbox execution through the **Noop adapter** (local policy-gated execution). Commands run via SafeCode's own `ShellRunner` (CommandPolicy + NetworkPolicy + FilesystemBoundary) when all preflight checks pass (proposal integrity, approval, command policy, network policy, filesystem boundary, backend capability). Sandbox execution approvals are **single-use** and **atomically claimed** before execution via `claim_for_execution()` (lock file + `os.replace`), closing the TOCTOU window between preflight and `ShellRunner.run()`. If claim fails, execution is blocked without invoking the shell. Blocked preflight does not consume the approval. Every execution attempt (successful, non-zero exit, or claim-blocked) writes a persistent, redacted/truncated `SandboxExecutionResultRecord` to `.sac/sandbox_executions/` and clears the pending proposal. Preflight-blocked attempts preserve the pending proposal for retry. CLI commands `sac sandbox executions` (with `--status`/`--backend`/`--proposal-id`/`--limit`/`--sort` filters, plus `stats` and `prune` subcommands), `sac sandbox execution show <id>`, and `sac sandbox last-execution` let users inspect and maintain past results. `prune` requires `--dry-run` or `--yes`, skips symlinks, and only deletes valid `.json` source files scanned under `.sac/sandbox_executions/`; a record cannot redirect deletion by claiming another `proposal_id`. Result records include a `_schema_version` marker for future migration and tolerate unknown fields for forward compatibility. `sac sandbox status` shows an execution results summary panel. macOS Seatbelt, Linux Bubblewrap, and Docker adapters remain dry-run only. No OS sandbox binary is ever invoked.

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
uv run sac --help
```

## Compatibility Requirements
- Keep sandbox execution disabled unless proposal, approval, policy, and preflight checks all allow it.
- Preserve diff review, checkpoint, audit, rollback, command policy, filesystem containment, network deny-by-default, and approval binding.
- Project-local configuration must not weaken user-level safety policy.
- Only Noop adapter supports real execution. macOS/Linux/Docker adapters must remain dry-run only.
- New historical details belong in docs and Git tags, not in additional `.claude/skills/v*` files.
