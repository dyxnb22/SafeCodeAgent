"""Built-in read-only subagent role presets."""

from __future__ import annotations

from dataclasses import dataclass


READ_ONLY_ROLE_TOOLS: tuple[str, ...] = (
    "list_files",
    "read_file",
    "grep_files",
    "search_files",
    "search_symbol",
    "find_references",
)


@dataclass(frozen=True)
class SubagentRole:
    """A product-level role preset for read-only subagent runs."""

    name: str
    purpose: str
    title_prefix: str
    instruction_template: str
    allowed_tools: tuple[str, ...] = READ_ONLY_ROLE_TOOLS
    readonly: bool = True

    def build_title(self, query: str) -> str:
        suffix = query.strip()[:80] or self.purpose
        return f"{self.title_prefix}: {suffix}"

    def build_instructions(self, query: str) -> str:
        return self.instruction_template.format(query=query.strip() or "(no specific query)")


ROLE_PRESETS: dict[str, SubagentRole] = {
    "explore": SubagentRole(
        name="explore",
        purpose="Map relevant files, symbols, tests, and risks before editing.",
        title_prefix="Explore",
        instruction_template=(
            "Read-only exploration. Goal: {query}\n\n"
            "Find the likely files, symbols, tests, and implementation risks. "
            "Do not propose or perform writes. Return concise findings."
        ),
    ),
    "review": SubagentRole(
        name="review",
        purpose="Inspect pending or described changes for bugs, safety risks, and missing tests.",
        title_prefix="Review",
        instruction_template=(
            "Read-only review. Target: {query}\n\n"
            "Inspect for behavioral bugs, safety regressions, missing tests, and scope creep. "
            "Do not modify files. Return prioritized findings."
        ),
    ),
    "scout": SubagentRole(
        name="scout",
        purpose="Search broad codebase context and summarize candidate locations.",
        title_prefix="Scout",
        instruction_template=(
            "Read-only codebase scouting. Search target: {query}\n\n"
            "Identify candidate directories, files, symbols, and follow-up questions. "
            "Keep the answer concise and avoid implementation changes."
        ),
    ),
}


def get_role(name: str) -> SubagentRole:
    """Return a built-in role preset by name."""
    try:
        return ROLE_PRESETS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown subagent role: {name}") from exc
