"""Load local skills from the skills directory."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    """One local skill package."""

    name: str
    path: Path
    instructions: str


class SkillLoader:
    """Discover skill folders containing SKILL.md."""

    def __init__(self, project_root: Path) -> None:
        self.skills_root = project_root / "skills"

    def list(self) -> list[Skill]:
        """List available skills."""
        if not self.skills_root.exists():
            return []
        skills: list[Skill] = []
        for skill_file in sorted(self.skills_root.glob("*/SKILL.md")):
            skills.append(
                Skill(
                    name=skill_file.parent.name,
                    path=skill_file.parent,
                    instructions=skill_file.read_text(encoding="utf-8"),
                )
            )
        return skills

    def get(self, name: str) -> Skill:
        """Read one skill by folder name."""
        for skill in self.list():
            if skill.name == name:
                return skill
        raise FileNotFoundError(f"Skill not found: {name}")
