# VERSION: short-feature-name

## Status
Planned.

## Base
- Depends on: `PREVIOUS_VERSION`
- Baseline context: `.claude/skills/current/SKILL.md`
- Runtime invariants: `.claude/skills/shared/core-runtime.md`
- New tag: `VERSION`

## Goals
- [ ] Goal 1
- [ ] Goal 2

## Requirements
- [ ] Requirement 1
- [ ] Requirement 2

## Backward Compatibility
- Preserve existing CLI commands unless this plan explicitly lists a breaking change.
- Preserve safety invariants from `.claude/skills/shared/core-runtime.md`.
- Keep migrations and state changes additive where possible.

## Implementation Notes
- Main files:
  - `src/safecode/...`
- New tests:
  - `tests/test_...py`

## Testing Checklist
- [ ] Targeted tests pass.
- [ ] `PYTHONPATH=src python3 -m pytest -q` passes.
- [ ] CLI smoke command passes when relevant.
- [ ] Version docs are updated.

## Acceptance Criteria
- [ ] All requirements are implemented.
- [ ] No safety boundary is weakened.
- [ ] Version note or implementation matrix entry is updated.

## Completion Notes
Fill this in after implementation:
- Implemented:
- Tests:
- Tag:
