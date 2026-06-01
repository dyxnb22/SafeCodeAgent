"""Release checklist rendering."""


def render_release_checklist(version: str) -> str:
    """Render a release checklist."""
    normalized = version if version.startswith("v") else f"v{version}"
    bare = normalized.removeprefix("v")
    return "\n".join(
        [
            f"# SafeCode Release Checklist {normalized}",
            "",
            "> [planning helper] This checklist is a human-readable guide, not a release gate.",
            "> The authoritative gate is: `sac release preflight`.",
            "",
            "## Version And Docs",
            "",
            f"- [ ] `sac release bump {bare}` updated all canonical version files",
            f"- [ ] `docs/version-notes/{normalized}-<summary>.md` exists",
            f"- [ ] `.claude/skills/current/SKILL.md` baseline mentions `{normalized}`",
            "- [ ] README/docs updated for any user-facing command changes",
            "",
            "## Verification",
            "",
            "- [ ] Focused tests for the changed area pass",
            "- [ ] `PYTHONPATH=src python3 -m pytest -q` passes",
            "- [ ] `PYTHONPATH=src python3 -m safecode.cli release check` passes",
            "- [ ] `PYTHONPATH=src python3 -m safecode.cli release smoke` passes",
            "- [ ] `PYTHONPATH=src python3 -m safecode.cli release meta` passes",
            "- [ ] `PYTHONPATH=src python3 -m safecode.cli release preflight` passes",
            "",
            "## Git",
            "",
            f"- [ ] `git commit -m \"Implement {normalized} <summary>\"`",
            f"- [ ] `git tag -a {normalized} -m \"{normalized} <summary>\"`",
            "- [ ] `git describe --exact-match --tags HEAD` prints the release tag",
            "- [ ] `git status --short --branch` shows a clean worktree",
        ]
    )
