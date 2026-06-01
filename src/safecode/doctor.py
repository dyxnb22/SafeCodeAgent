"""Environment checks for install and update polish."""

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from safecode import __version__
from safecode.release.docs_guard import check_docs_finalized
from safecode.release.preflight import run_release_preflight
from safecode.release.version_guard import check_tag_consistency, check_version_consistency


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
        checks = [
            DoctorCheck("python", sys.version_info >= (3, 11), sys.version.split()[0]),
            DoctorCheck("uv", shutil.which("uv") is not None, shutil.which("uv") or "not found"),
            DoctorCheck("project_root", self.project_root.exists(), str(self.project_root)),
            DoctorCheck("pyproject", (self.project_root / "pyproject.toml").exists(), "pyproject.toml"),
            DoctorCheck("config", (self.project_root / ".sac" / "config.toml").exists(), ".sac/config.toml"),
            DoctorCheck("sac_dir", (self.project_root / ".sac").exists(), ".sac"),
            DoctorCheck("approval_dir", bool(os.getenv("SAFECODE_APPROVAL_DIR")), os.getenv("SAFECODE_APPROVAL_DIR", "not set")),
            DoctorCheck(
                "sandbox_approval_dir",
                bool(os.getenv("SAFECODE_SANDBOX_APPROVAL_DIR")),
                os.getenv("SAFECODE_SANDBOX_APPROVAL_DIR", "not set"),
            ),
        ]
        checks.extend(self._release_checks())
        return checks

    def _release_checks(self) -> list[DoctorCheck]:
        """Run release diagnostics without mutating the checkout."""
        version = check_version_consistency(
            pyproject_path=self.project_root / "pyproject.toml",
            runtime_version=__version__,
        )
        tag = check_tag_consistency(version.package_version, project_root=self.project_root)
        docs = check_docs_finalized(__version__, project_root=self.project_root)
        preflight = run_release_preflight(self.project_root)

        return [
            DoctorCheck(
                "release_version",
                version.ok,
                version.message,
            ),
            DoctorCheck(
                "release_tag",
                tag.consistent,
                tag.message,
            ),
            DoctorCheck(
                "release_docs",
                docs.ok,
                "docs finalized" if docs.ok else "; ".join(docs.issues),
            ),
            DoctorCheck(
                "release_preflight",
                preflight.ok,
                "preflight passed" if preflight.ok else "preflight needs attention",
            ),
        ]
