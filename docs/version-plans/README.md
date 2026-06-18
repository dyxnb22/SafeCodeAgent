# Version Plans

This directory is for active or draft version-specific plans. Git tags define
the real code baseline for completed versions; `docs/release-ledger.md` keeps
the compact completion ledger.

## Current Planning

No active version plan is currently open. Start a new plan from
[_template.md](_template.md), keep it here while the work is active, and move the
result into the release ledger when the work ships.

## Completed Planning

Completed roadmaps were consolidated into
[../planning-history.md](../planning-history.md). Use that page for compact
planning context, [../release-ledger.md](../release-ledger.md) for shipped
release history, and
[../version_implementation_matrix.md](../version_implementation_matrix.md) for
detailed implementation archaeology.

## New Plans

Create a plan and matching ledger stub with:

```bash
scripts/new-version-plan.sh v1.8.0 v1.7.9 short-feature-name
```

Then edit:

```text
docs/version-plans/v1.8.0-short-feature-name.md
docs/release-ledger.md
```

Use [_template.md](_template.md) for requirements, acceptance criteria, tests,
and compatibility constraints.

## Completion Checklist

- [ ] Version plan reflects the final implementation or links to final notes.
- [ ] `docs/release-ledger.md` has a `## <version>` completion entry.
- [ ] `docs/version_implementation_matrix.md` lists the version if it is part
  of a roadmap train.
- [ ] `.claude/skills/current/SKILL.md` and `.claude/versions.json` point at
  the new implemented tag after the tag becomes the baseline.
- [ ] Targeted tests pass.
- [ ] `PYTHONPATH=src python3 -m pytest -q` passes for cross-cutting changes.
- [ ] Git tag is created only after tests and docs are ready.
