# SafeCode Agent Global Context

## Project
- Name: SafeCode Agent
- Purpose: safety-first Python terminal coding agent and local runtime.
- Core loop: collect context -> propose patch -> preview diff -> approve -> checkpoint -> apply -> audit -> rollback.

## Stack
- Runtime: Python 3.11+
- Package manager: `uv`
- CLI: Typer, entrypoint `sac`
- Models/config: Pydantic
- Tests: pytest

## Quick Commands
- Install dependencies: `uv sync`
- Run CLI help: `uv run sac --help`
- Run local doctor: `uv run sac doctor`
- Run full tests locally: `PYTHONPATH=src python3 -m pytest -q`
- Run CI-equivalent tests after install: `python -m pytest -q`
- Build package: `uv build`
- Show recent runtime errors: `uv run sac logs show --level error --traceback`
- Generate a version plan: `scripts/new-version-plan.sh vX.Y.Z vPREV short-feature-name`
- Generate a version skill alias: `scripts/new-version-skill.sh vX.Y.Z vPREV short-feature-name`

Common development flow:
1. Read the relevant version plan and source-of-truth files below.
2. Make a small, reviewable change that preserves existing command names and safety gates.
3. Run targeted tests for the touched module.
4. Run `PYTHONPATH=src python3 -m pytest -q` before completing cross-cutting work.
5. Update version plans/notes and `.claude/skills/current/SKILL.md` when version behavior changes.

CI currently installs with `python -m pip install -e ".[dev]"` and runs `python -m pytest -q`.
There is no Makefile in this repository.

## Directory Map
- `src/safecode/` - Main Python package.
  - `agent/` - Agent session state, loop, structured schemas, prompts, approvals, and orchestration.
  - `audit/` - Audit event models, hash-chain logger, and anchor verification.
  - `checkpoint/` - Checkpoint metadata and rollback manager.
  - `cli.py`, `cli_*.py` - Typer entrypoint and focused command groups.
  - `context/` - Safe context collection, budget packing, redaction, and source selection.
  - `demo/` - Repeatable demo workflow definitions.
  - `hooks/` - Hook execution and approval state.
  - `index/` - File, Python symbol, and repository map indexing.
  - `llm/` - Mock and OpenAI-compatible LLM clients plus provider factory.
  - `mcp/` - MCP discovery, read-only runner, and write proposal flow.
  - `patch/` - Patch parser, models, validator, diff builder, and applier.
  - `policy/` - Command policy rules.
  - `project/` - Project rules and test/build command detection.
  - `sandbox/` - Sandbox adapters, backend planning, approval state, preflight, and execution gate.
  - `shell/` - Shell risk classification and policy-gated runner.
  - `state/` - Progress and per-session task journals.
  - `subagents/` - File-backed subagent tasks, read-only runner, and merge review.
  - `tools/` - Internal tool metadata registry.
- `tests/` - Pytest suite, with broad security, sandbox, policy, audit, patch, and CLI coverage.
- `docs/` - Roadmaps, version plans, version notes, and user guide.
- `examples/` - Demo projects and generated workflow seeds.
- `skills/` - Project-local skills for Python CLI and FastAPI work.
- `scripts/` - Version plan/skill scaffolding helpers.
- `.github/workflows/ci.yml` - CI install and test workflow.
- `.claude/` - Claude context, rules, skills, and version index.

## Code Standards
- Use type hints for new or changed public functions and dataclasses/Pydantic models.
- Prefer small, reviewable changes with focused tests.
- Keep CLI behavior deterministic in tests; default LLM provider must remain `mock`.
- Preserve existing command names and documented flows unless a version plan declares a breaking change.
- Use structured parsing and typed models for policy/security state instead of ad hoc string handling.
- Add or update tests for every security, sandbox, policy, patch, audit, approval, or rollback change.
- For narrow changes, run targeted tests first; for cross-cutting changes, run the full regression command.
- Keep project-local config untrusted when it attempts to weaken user-level safety policy.

## Source Of Truth
- Version index: `docs/version_implementation_matrix.md`
- Release roadmap: `docs/release_roadmap_v0_1_to_v1_0.md`
- Current runtime summary: `.claude/skills/shared/core-runtime.md`
- Current implementation baseline: `.claude/skills/current/SKILL.md`
- Implemented tag index: `.claude/versions.json`
- General rules: `.claude/rules/general-rules.md`

## Version Workflow
When asked to implement `vX.Y.Z`:
1. Read `.claude/skills/current/SKILL.md` and `.claude/skills/shared/core-runtime.md`.
2. Check the base tag and version history in `.claude/versions.json`, `docs/version_implementation_matrix.md`, and Git tags.
3. Use the previous tag as the code baseline and preserve backward-compatible safety behavior unless the version plan explicitly says otherwise.
4. Add or update tests for every security, sandbox, policy, patch, audit, or approval change.
5. Update docs/version notes and `.claude/skills/current/SKILL.md` when the version is completed.

Keep this file small. Put historical details in `docs/` and Git tags, not in `.claude`.

## Critical Safety Rules
- **Never bypass diff review, checkpoint, audit, rollback, policy, or sandbox gates for convenience.**
- **Never let project-local configuration lower user-level safety policy.**
- **Default network and write capabilities to denied unless an explicit trusted path enables them.**
- **Keep approval stores, audit anchors, and trust roots outside project-controlled paths.**
- **Preserve rollback capability for every file-writing workflow.**
- **MCP write operations and sandbox execution must stay proposal/approval gated.**
