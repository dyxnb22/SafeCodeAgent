---
name: Current SafeCode Agent Baseline
description: >
  Current implemented SafeCode Agent baseline. Read this with the shared
  runtime summary before implementing the next version.
---

# Current Baseline - v2.0.2

## Status
Implemented and tagged as `v2.0.2`.

## Stage
`v2.0.x` Usable Local Coding Agent MVP.

## Source Of Truth
- Version index: `docs/version_implementation_matrix.md`
- Release roadmap: `docs/release_roadmap_v0_1_to_v1_0.md`
- Git baseline: tag `v2.0.2`
- Runtime invariants: `.claude/skills/shared/core-runtime.md`

## Current Capability
SafeCode Agent has a safety-first local runtime centered on controlled file edits, command policy, audit, rollback, and sandbox planning.

The current baseline extends `v2.0.1` by adding durable per-session task journals. Agent sessions now write JSONL timelines under `.sac/agent_journals/` for plan, action, failure, and final-summary events, with reusable diff and command event helpers ready for upcoming workflow layers. `sac agent journal [session_id]` renders a session timeline as Markdown, and task reports include a compact latest-journal summary. Context budget metadata from `v2.0.1` remains in place. Real-model validation still requires `OPENAI_API_KEY` or `SAFECODE_LLM_API_KEY`, plus the existing network allow policy. Tests and normal local development remain keyless through mock mode.

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
