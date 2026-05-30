# SafeCode Agent General Rules

## Safety
- Never bypass diff review, checkpoint, audit, rollback, policy, or sandbox gates for convenience.
- Treat project-local configuration as untrusted when it attempts to weaken user-level safety policy.
- Default network and write capabilities to denied unless an explicit trusted path enables them.
- Keep approval stores, audit anchors, and trust roots outside project-controlled paths.

## Implementation
- Prefer small, reviewable changes with focused tests.
- Keep CLI behavior deterministic in tests; default LLM provider should remain `mock`.
- Preserve existing command names and documented flows unless a version plan declares a breaking change.
- Use structured parsing and typed models for policy/security state instead of ad hoc string handling.

## Verification
- Default full regression command: `PYTHONPATH=src python3 -m pytest -q`.
- For narrow changes, run the closest targeted tests first, then full tests when risk is cross-cutting.
- Update `docs/version_implementation_matrix.md` and `docs/version-notes/` when a version changes behavior or acceptance commands.

## Git
- Branch names for this repository intentionally do not use the `codex/` prefix.
- Prefer `vX.Y.Z-short-feature-name` or `work/vX.Y.Z` for version branches.
