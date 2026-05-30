# Tag + Skill Version Workflow

This repository uses a lightweight three-layer version workflow:

1. `.claude/CLAUDE.md` keeps small global project context.
2. `.claude/skills/<version>/SKILL.md` keeps version-specific requirements.
3. Git tags define the real code baseline for each completed version.

The goal is to keep each new implementation session focused on the current version instead of reloading the full project history.

## Files

- `.claude/CLAUDE.md`: global project context, stack, source-of-truth pointers, and workflow.
- `.claude/rules/general-rules.md`: stable coding, safety, verification, and git rules.
- `.claude/versions.json`: machine-readable version ranges and latest implemented version.
- `.claude/skills/shared/core-runtime.md`: stable SafeCode runtime invariants.
- `.claude/skills/<version>/SKILL.md`: requirements and acceptance criteria for a specific version.
- `.claude/skills/_template/SKILL.md`: template for a new version skill.
- `docs/version_implementation_matrix.md`: human-readable version index and acceptance commands.
- `docs/version-notes/`: completion notes for individual versions.

## Start A New Version

Create a skill and matching version note:

```bash
scripts/new-version-skill.sh v1.8.0 v1.7.9 short-feature-name
```

Then edit:

```text
.claude/skills/v1.8.0/SKILL.md
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
- `.claude/skills/v1.8.0/SKILL.md`
- `.claude/skills/shared/core-runtime.md`

Then implement the version, run targeted tests, run the relevant regression suite, and update the version notes.
```

## Completion Checklist

- [ ] Version skill reflects the final implementation.
- [ ] `docs/version-notes/<version>-<name>.md` has completion notes.
- [ ] `docs/version_implementation_matrix.md` lists the version if it is part of the roadmap.
- [ ] Targeted tests pass.
- [ ] `PYTHONPATH=src python3 -m pytest -q` passes for cross-cutting changes.
- [ ] Git tag is created only after tests and docs are ready.
