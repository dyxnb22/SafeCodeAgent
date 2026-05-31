---
name: Current SafeCode Agent Baseline
description: >
  Current implemented SafeCode Agent baseline. Read this with the shared
  runtime summary before implementing the next version.
---

# Current Baseline - v2.0.3

## Status
Implemented and tagged as `v2.0.3`.

## Stage
`v2.0.x` Usable Local Coding Agent MVP.

## Source Of Truth
- Version index: `docs/version_implementation_matrix.md`
- Release roadmap: `docs/release_roadmap_v0_1_to_v1_0.md`
- Git baseline: tag `v2.0.3`
- Runtime invariants: `.claude/skills/shared/core-runtime.md`

## Current Capability
SafeCode Agent has a safety-first local runtime centered on controlled file edits, command policy, audit, rollback, and sandbox planning.

The current baseline extends `v2.0.2` by adding project test detection and policy-gated test execution. `sac test detect` now identifies likely pytest, uv pytest, npm, and pnpm test commands and shows their command-policy proposal status without executing anything. `sac test run` can run a detected or explicit test command through the same `ShellRunner`, approval checkpoint, runtime log, and audit boundaries as controlled shell execution. Context budget metadata, task journals, and the real-LLM contract remain in place. Real-model validation still requires `OPENAI_API_KEY` or `SAFECODE_LLM_API_KEY`, plus the existing network allow policy. Tests and normal local development remain keyless through mock mode.

## Important Entry Points
- `src/safecode/cli.py`
- `src/safecode/agent/approvals.py`
- `src/safecode/agent/loop.py`
- `src/safecode/agent/schemas.py`
- `src/safecode/agent/session.py`
- `src/safecode/agent/tools.py`
- `src/safecode/context/budget.py`
- `src/safecode/context/collector.py`
- `src/safecode/context/selector.py`
- `src/safecode/project/test_detector.py`
- `src/safecode/state/journal.py`
- `src/safecode/llm/base.py`
- `src/safecode/llm/mock.py`
- `src/safecode/llm/openai_client.py`
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
PYTHONPATH=src python3 -m pytest tests/test_agent_journal.py tests/test_agent_session.py -q
PYTHONPATH=src python3 -m pytest tests/test_project_test_detector.py -q
PYTHONPATH=src python3 -m pytest tests/test_context_budget.py -q
PYTHONPATH=src python3 -m pytest tests/test_agent_contract.py tests/test_agent_tool_intents.py -q
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
- Real LLM calls must keep network policy and API key requirements explicit; mock mode must remain available for keyless tests.
- Context collection must remain bounded and redacted; budget metadata should explain truncation without exposing hidden content.
- Agent journals must validate session ids and remain summaries rather than hidden context dumps.
- Test detection must not execute commands; `sac test run` must reuse shell policy, approval, and audit gates.
