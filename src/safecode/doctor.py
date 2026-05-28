"""Environment checks for v1.0 install polish."""

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DoctorCheck:
    """One doctor check."""

    name: str
    passed: bool
    detail: str


class Doctor:
    """Check whether the local environment can run SafeCode."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def run(self) -> list[DoctorCheck]:
        """Run checks."""
        return [
            DoctorCheck("python", sys.version_info >= (3, 11), sys.version.split()[0]),
            DoctorCheck("uv", shutil.which("uv") is not None, shutil.which("uv") or "not found"),
            DoctorCheck("project_root", self.project_root.exists(), str(self.project_root)),
            DoctorCheck("pyproject", (self.project_root / "pyproject.toml").exists(), "pyproject.toml"),
        ]
