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
