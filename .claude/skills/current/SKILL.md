---
name: Current SafeCode Agent Baseline
description: >
  Current implemented SafeCode Agent baseline. Read this with the shared
  runtime summary before implementing the next version.
---

# Current Baseline - v2.2.1

## Status
Implemented and tagged as `v2.2.1`.

## Stage
`v2.2.x` Tool Ecosystem.

## Source Of Truth
- Version index: `docs/version_implementation_matrix.md`
- Release roadmap: `docs/release_roadmap_v0_1_to_v1_0.md`
- Git baseline: tag `v2.2.1`
- Runtime invariants: `.claude/skills/shared/core-runtime.md`

## Current Capability
SafeCode Agent has a safety-first local runtime centered on controlled file edits, command policy, audit, rollback, and sandbox planning.

The `v2.1.x` stage added repository intelligence on top of the `v2.0.x` MVP:

**v2.1.0 (Code Map):** A repo map builder under `src/safecode/index/` indexes safe files, Python class/function symbols, imports, likely test files with detected test commands, and project script entrypoints (`__main__` guards). `sac index map` outputs a summary or JSON representation. Existing file and symbol indexes remain compatible.

**v2.1.1 (Test/Build Detector):** Extended `src/safecode/project/test_detector.py` to cover pytest, uv pytest, npm/pnpm test/build/lint scripts, Gradle (`./gradlew` preferred), Maven, Go, Cargo, and Python Ruff lint detection. Detection remains proposal-only; execution is still gated by shell policy. `sac test detect` renders policy status without executing; `sac test run` prefers a policy-runnable detected candidate.

**v2.1.2 (Runtime Consolidation):** `src/safecode/cli.py` is now a slim Typer registry; command implementations live in focused `src/safecode/cli_*.py` modules (cli_agent, cli_core, cli_mcp, cli_ops, cli_project, cli_sandbox, cli_shared, cli_subagent, cli_test_demo) — public command names are unchanged. `AgentLoop` now calls `LLMClient.plan()` to create session plans and `LLMClient.choose_tool()` before routing each step through `ToolIntentRouter`. `ContextCollector.collect(query=...)` adds compact repo-map summaries and query-selected context snippets while preserving budget metadata and source lists. Placeholder path and project-detection helpers now fail closed or return a concrete label. Package version and version matrix entries are synchronized to `2.1.2`.

**v2.1.3 (Diff Planner):** `src/safecode/agent/planner.py` adds `DiffPlanner` with `predict(task, context_hint="")` and `compare(plan, proposal)`. `predict()` extracts file-path tokens from task text using a regex (word-boundary + lookbehind `(?<![:/.])` to reject URL fragments); no LLM call. `compare()` produces a `DiffScopeResult` with a `Literal` status: `no_prediction` (vague task), `match`, `within_scope`, or `extra_files`. Duplicate blocks for the same file are deduplicated before comparison. The `patch_proposed` audit event now carries `scope_status` and, when applicable, `scope_warning` in its metadata. `sac edit` prints the warning in yellow after the diff preview. The scope check is advisory only — valid patches are never blocked by it.

**v2.1.4 (Context Debug Command):** `src/safecode/cli_context.py` adds a `context_app` Typer group registered under `sac context`. The `sac context explain "task"` command is read-only and LLM-free: it calls `ContextSelector.select_sources()` to rank and explain file selection, reads budget limits from `SafeCodeConfig`, and calls `RepoMapBuilder.build()` for repository statistics. Output sections: Context Selection (ranked table with score and reason), Budget Metadata (max bytes/tokens), and Repo Map (counts). Sensitive files are excluded via existing `FileIndexer` skip rules. No writes to `.sac/` or any project path.

**v2.2.1 (Model Tool Call Adapter):** `src/safecode/tools/adapter.py` adds `ToolCallAdapter` with `validate(tool_name, args)` and `lookup(tool_name)`. `validate()` checks name existence in `ToolRegistry`, required arg presence, and arg types; raises `AdapterError` (a `ValueError` subclass) on any failure. Returns frozen `ToolCallValidationResult` with `tool_name`, `spec`, `resolved_args`, `requires_approval`, `risk`, `permission_category`, and `audit_event`. `ToolIntentRouter` in `src/safecode/agent/tools.py` now calls `ToolCallAdapter.lookup()` for every intent type via a `_REGISTRY_NAMES` mapping; approval is derived from `ToolSpec.requires_human_approval` (authoritative) OR the intent flag. MCP intents default to `mcp.propose_write` (conservative). Unknown registry names fail closed. All public route strings and CLI behavior are unchanged.

**v2.2.0 (Tool Schema Registry):** `src/safecode/tools/registry.py` is rewritten with a complete schema layer. New models: `ToolRiskLevel` (StrEnum: low/medium/high), `PermissionCategory` (StrEnum: read/write/shell/sandbox/mcp/subagent/audit), `ToolArgSchema` (frozen Pydantic: name/type/required/description), `AuditEventRef` (frozen Pydantic: event_type/description), `ToolSpec` (frozen Pydantic: full tool metadata). `ToolRegistry` provides `list()`, `get(name)`, `names()`, `by_permission()`, `by_risk()`, and `requiring_approval()`. 16 internal tools are registered covering the full read/write/shell/sandbox/mcp/subagent/audit surface. Registry is deterministic, keyless, and produces no side effects. `sac tools list` expanded to show Name/Risk/Permission/Approval/Description with `--risk` and `--permission` filters. New `sac tools inspect TOOL_NAME` shows full schema in a rich panel.

## Important Entry Points
- `src/safecode/cli.py` — slim Typer registry; imports from cli_*.py modules
- `src/safecode/cli_context.py`
- `src/safecode/tools/adapter.py`
- `src/safecode/tools/registry.py`
- `src/safecode/cli_agent.py`
- `src/safecode/cli_core.py`
- `src/safecode/cli_ops.py`
- `src/safecode/cli_project.py`
- `src/safecode/cli_sandbox.py`
- `src/safecode/cli_subagent.py`
- `src/safecode/cli_test_demo.py`
- `src/safecode/index/repo_map.py`
- `src/safecode/index/files.py`
- `src/safecode/index/python_symbols.py`
- `src/safecode/project/test_detector.py`
- `src/safecode/agent/planner.py`
- `src/safecode/agent/loop.py`
- `src/safecode/agent/approvals.py`
- `src/safecode/agent/schemas.py`
- `src/safecode/agent/session.py`
- `src/safecode/agent/tools.py`
- `src/safecode/context/collector.py`
- `src/safecode/context/selector.py`
- `src/safecode/context/budget.py`
- `src/safecode/state/journal.py`
- `src/safecode/llm/base.py`
- `src/safecode/llm/mock.py`
- `src/safecode/llm/openai_client.py`
- `src/safecode/sandbox/execution.py`
- `src/safecode/sandbox/preflight.py`
- `src/safecode/sandbox/adapter.py`
- `src/safecode/policy/commands.py`
- `src/safecode/shell/`
- `src/safecode/audit/`
- `tests/test_sandbox_execution_security_evals.py`

## Verification
```bash
PYTHONPATH=src python3 -m pytest tests/test_tool_call_adapter.py -q
PYTHONPATH=src python3 -m pytest tests/test_tool_schema_registry.py -q
PYTHONPATH=src python3 -m pytest tests/test_context_explain.py -v
PYTHONPATH=src python3 -m pytest tests/test_repo_map.py -q
PYTHONPATH=src python3 -m pytest tests/test_project_test_detector.py -q
PYTHONPATH=src python3 -m pytest tests/test_diff_planner.py -v
PYTHONPATH=src python3 -m pytest tests/test_agent_session.py tests/test_agent_journal.py tests/test_context_budget.py -q
PYTHONPATH=src python3 -m pytest tests/test_agent_contract.py tests/test_agent_tool_intents.py -q
PYTHONPATH=src python3 -m pytest tests/test_sandbox_execution_security_evals.py -q
PYTHONPATH=src python3 -m pytest -q
uv run sac --help
```

## Compatibility Requirements (v2.2.1 additions)
- `ToolCallAdapter.validate()` is validation/adaptation only — it must not execute tools or call the LLM.
- `ToolCallValidationResult` is frozen; callers must not construct mutable copies.
- `AdapterError` is a `ValueError` subclass — callers catching `ValueError` will catch it.
- `ToolIntentRouter` backward compat: all existing route strings and `RoutedToolIntent` fields are unchanged.
- `requires_human_approval` from `ToolSpec` is always respected; registry metadata is authoritative.

## Compatibility Requirements (v2.2.0 additions)
- Tool schema registry is schema/metadata only; no tool execution is performed by the registry layer.
- `ToolSpec`, `ToolArgSchema`, and `AuditEventRef` are frozen Pydantic models — callers must not construct mutable copies.
- High-risk tools must carry `requires_human_approval=True`; WRITE and SHELL permission tools must too.
- `ToolRegistry.get()` raises `KeyError` for unknown names — callers must not swallow this without logging.

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
- Repo map and context selection must not bypass redaction or budget limits when incorporating repository intelligence.
- Test/build detection is proposal-only; detected commands must not be executed without going through shell policy and approval gates.
- CLI module split must not change existing public command names or weaken any safety gate.
- Diff planner scope check is advisory only; it must never block or modify a valid patch.
- `DiffScopeResult.status` must remain a constrained `Literal` — callers must not construct results with arbitrary status strings.
