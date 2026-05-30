# SafeCode Agent Core Runtime

SafeCode Agent is a safety-first Python CLI and local agent runtime. The current production shape is centered on controlled file edits, command execution, policy enforcement, auditability, rollback, and sandbox planning.

## Stable User Commands
- `sac ask "..."` collects context and answers using the configured LLM provider.
- `sac edit "..."` proposes a pending patch without directly changing project files.
- `sac apply` validates and applies a pending patch through checkpoint and audit.
- `sac rollback --last` restores from the latest checkpoint.
- `sac history` shows audited actions.
- `sac run "..." --yes` runs allowed commands through policy checks.
- `sac logs show --level error --traceback` inspects runtime failures.
- `sac doctor` checks local installation health.
- `sac sandbox plan|propose|pending|execute|approve|approvals|revoke|preflight` manages sandbox planning and execution gates.

## Core Safety Invariants
- File writes must go through patch parsing, validation, diff preview, checkpoint, apply, and audit.
- High-risk shell commands stay blocked even with `--yes`.
- Shell commands run via argv execution, not shell string execution.
- Shell, hooks, and read-only MCP execution go through command policy checks.
- Project config cannot reduce user-level safety policy.
- Context collection must skip secret-like files and redact secret-like content.
- Network access is disabled by default and enforced for shell, MCP, and real LLM calls.
- MCP write operations produce proposals instead of direct execution.
- Approval stores and audit anchors must live outside the project root.
- Sandbox execution remains gated by proposal, approval, preflight, and policy state.

## Important Entry Points
- CLI: `src/safecode/cli.py`
- Agent flow: `src/safecode/agent/orchestrator.py`
- Patch model/parser/validator/applier: `src/safecode/patch/`
- Checkpoints: `src/safecode/checkpoint/`
- Audit and anchors: `src/safecode/audit/`
- Command policy and shell runner: `src/safecode/policy/commands.py`, `src/safecode/shell/`
- Context collection/redaction: `src/safecode/context/`
- Sandbox planning/execution/preflight: `src/safecode/sandbox/`
- MCP runner/proposals: `src/safecode/mcp/`
- Subagents: `src/safecode/subagents/`
- Runtime logs: `src/safecode/logs/runtime.py`

## Verification
- Full regression: `PYTHONPATH=src python3 -m pytest -q`
- Install/health: `uv run sac doctor`
- CLI smoke: `uv run sac --help`
