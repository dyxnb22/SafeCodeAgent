"""Release checklist rendering."""


def render_release_checklist(version: str) -> str:
    """Render a release checklist."""
    return "\n".join(
        [
            f"# SafeCode Release Checklist {version}",
            "",
            "- [ ] Tests pass",
            "- [ ] `sac --help` works",
            "- [ ] Demo project flow works",
            "- [ ] Version note exists",
            "- [ ] Security defaults reviewed",
            "- [ ] README updated",
        ]
    )
