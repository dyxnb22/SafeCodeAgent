# Tag + Version Plan Workflow

This repository uses a lightweight three-layer version workflow:

1. `.claude/CLAUDE.md` keeps small global project context.
2. `docs/version-plans/<version>-<name>.md` keeps planned version-specific requirements.
3. Git tags define the real code baseline for each completed version.

The goal is to keep each new implementation session focused on the current baseline instead of reloading the full project history.

## Files

- `.claude/CLAUDE.md`: global project context, stack, source-of-truth pointers, and workflow.
- `.claude/rules/general-rules.md`: stable coding, safety, verification, and git rules.
- `.claude/versions.json`: compact machine-readable pointers, version ranges, and latest implemented tag.
- `.claude/skills/current/SKILL.md`: current implemented baseline for agent sessions.
- `.claude/skills/shared/core-runtime.md`: stable SafeCode runtime invariants.
- `docs/version-plans/`: planned version requirements and acceptance criteria.
- `docs/version-plans/_template.md`: reusable version plan template.
- `docs/version_implementation_matrix.md`: human-readable version index and acceptance commands.
- `docs/version-notes/`: completion notes for individual versions.

## Start A New Version

Create a version plan and matching completion note:

```bash
scripts/new-version-plan.sh v1.8.0 v1.7.9 short-feature-name
```

Then edit:

```text
docs/version-plans/v1.8.0-short-feature-name.md
docs/version-notes/v1.8.0-short-feature-name.md
```

Fill in concrete goals, requirements, tests, acceptance criteria, and any compatibility constraints before implementation starts.

## Suggested Branch Flow

```bash
git checkout v1.7.9
git checkout -b work/v1.8.0
```

After implementation and verification:

```bash
git checkout main
git merge work/v1.8.0 --ff-only
git tag -a v1.8.0 -m "v1.8.0: short feature name"
git push origin main v1.8.0
```

This repository's existing roadmap says version branches should not use the `codex/` prefix.

## Prompt Template

```markdown
# Implement v1.8.0

I created the working branch from tag v1.7.9.
Please read:

- `.claude/CLAUDE.md`
- `.claude/skills/current/SKILL.md`
- `.claude/skills/shared/core-runtime.md`
- `docs/version-plans/v1.8.0-short-feature-name.md`

Then implement the version, run targeted tests, run the relevant regression suite, and update the version notes.
```

## Completion Checklist

- [ ] Version plan reflects the final implementation or links to the final notes.
- [ ] `docs/version-notes/<version>-<name>.md` has completion notes.
- [ ] `docs/version_implementation_matrix.md` lists the version if it is part of the roadmap.
- [ ] `.claude/skills/current/SKILL.md` is updated after the tag becomes the new baseline.
- [ ] `.claude/versions.json` has the new `current_implemented_tag`.
- [ ] Targeted tests pass.
- [ ] `PYTHONPATH=src python3 -m pytest -q` passes for cross-cutting changes.
- [ ] Git tag is created only after tests and docs are ready.
