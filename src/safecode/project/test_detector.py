"""Detect likely project test commands."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestCommandCandidate:
    """One detected test command with a short explanation."""

    command: str
    tool: str
    reason: str
    confidence: str = "medium"


class ProjectTestDetector:
    """Detect common test commands from local project manifests."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def detect(self) -> list[TestCommandCandidate]:
        """Return likely test commands in deterministic priority order."""
        candidates: list[TestCommandCandidate] = []
        candidates.extend(self._detect_python())
        candidates.extend(self._detect_node())
        candidates.extend(self._detect_gradle())
        candidates.extend(self._detect_maven())
        candidates.extend(self._detect_go())
        candidates.extend(self._detect_cargo())
        return _dedupe_commands(candidates)

    def _detect_python(self) -> list[TestCommandCandidate]:
        candidates: list[TestCommandCandidate] = []
        pyproject = self.project_root / "pyproject.toml"
        has_pytest_ini = any((self.project_root / name).exists() for name in ("pytest.ini", "tox.ini", "setup.cfg"))
        has_tests_dir = (self.project_root / "tests").is_dir()
        pyproject_mentions_pytest = self._pyproject_mentions_pytest(pyproject)
        if not (pyproject.exists() or has_pytest_ini or has_tests_dir):
            return candidates

        if (self.project_root / "uv.lock").exists():
            candidates.append(
                TestCommandCandidate(
                    command="uv run pytest -q",
                    tool="uv",
                    reason="uv.lock detected with Python test markers.",
                    confidence="high" if pyproject_mentions_pytest or has_tests_dir else "medium",
                )
            )

        if pyproject_mentions_pytest or has_pytest_ini or has_tests_dir:
            candidates.append(
                TestCommandCandidate(
                    command="pytest -q",
                    tool="pytest",
                    reason="pytest configuration or tests directory detected.",
                    confidence="high",
                )
            )
        if self._python_mentions_ruff(pyproject):
            if (self.project_root / "uv.lock").exists():
                candidates.append(
                    TestCommandCandidate(
                        command="uv run ruff check .",
                        tool="uv",
                        reason="uv.lock detected with Ruff configuration or dependency.",
                        confidence="medium",
                    )
                )
            candidates.append(
                TestCommandCandidate(
                    command="ruff check .",
                    tool="ruff",
                    reason="Ruff configuration or dependency detected.",
                    confidence="medium",
                )
            )
        return candidates

    def _pyproject_mentions_pytest(self, pyproject: Path) -> bool:
        if not pyproject.exists():
            return False
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return False
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return "pytest" in text.lower()

        project = data.get("project", {})
        optional = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
        dependency_groups = data.get("dependency-groups", {})
        tool = data.get("tool", {})
        if isinstance(tool, dict) and "pytest" in tool:
            return True
        serialized = json.dumps([project.get("dependencies", []), optional, dependency_groups]).lower()
        return "pytest" in serialized

    def _python_mentions_ruff(self, pyproject: Path) -> bool:
        if (self.project_root / "ruff.toml").exists() or (self.project_root / ".ruff.toml").exists():
            return True
        if not pyproject.exists():
            return False
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return False
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return "ruff" in text.lower()

        project = data.get("project", {})
        optional = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
        dependency_groups = data.get("dependency-groups", {})
        tool = data.get("tool", {})
        if isinstance(tool, dict) and "ruff" in tool:
            return True
        serialized = json.dumps([project.get("dependencies", []), optional, dependency_groups]).lower()
        return "ruff" in serialized

    def _detect_node(self) -> list[TestCommandCandidate]:
        package_json = self.project_root / "package.json"
        if not package_json.exists():
            return []
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        scripts = data.get("scripts", {})
        if not isinstance(scripts, dict) or "test" not in scripts:
            scripts = scripts if isinstance(scripts, dict) else {}
        tool = "pnpm" if (self.project_root / "pnpm-lock.yaml").exists() else "npm"
        candidates: list[TestCommandCandidate] = []
        for script_name in ("test", "build", "lint"):
            if script_name not in scripts:
                continue
            command = f"{tool} test" if script_name == "test" else f"{tool} run {script_name}"
            candidates.append(
                TestCommandCandidate(
                    command=command,
                    tool=tool,
                    reason=f"package.json {script_name} script detected.",
                    confidence="high" if script_name == "test" else "medium",
                )
            )
        return candidates

    def _detect_gradle(self) -> list[TestCommandCandidate]:
        markers = ("settings.gradle", "settings.gradle.kts", "build.gradle", "build.gradle.kts")
        if not any((self.project_root / marker).exists() for marker in markers):
            return []
        executable = "./gradlew" if (self.project_root / "gradlew").exists() else "gradle"
        return [
            TestCommandCandidate(
                command=f"{executable} test",
                tool="gradle",
                reason="Gradle build file detected.",
                confidence="high",
            ),
            TestCommandCandidate(
                command=f"{executable} build",
                tool="gradle",
                reason="Gradle build file detected.",
                confidence="medium",
            ),
        ]

    def _detect_maven(self) -> list[TestCommandCandidate]:
        if not (self.project_root / "pom.xml").exists():
            return []
        return [
            TestCommandCandidate(
                command="mvn test",
                tool="maven",
                reason="Maven pom.xml detected.",
                confidence="high",
            ),
            TestCommandCandidate(
                command="mvn package",
                tool="maven",
                reason="Maven pom.xml detected.",
                confidence="medium",
            ),
        ]

    def _detect_go(self) -> list[TestCommandCandidate]:
        if not (self.project_root / "go.mod").exists():
            return []
        return [
            TestCommandCandidate(
                command="go test ./...",
                tool="go",
                reason="go.mod detected.",
                confidence="high",
            ),
            TestCommandCandidate(
                command="go vet ./...",
                tool="go",
                reason="go.mod detected.",
                confidence="medium",
            ),
        ]

    def _detect_cargo(self) -> list[TestCommandCandidate]:
        if not (self.project_root / "Cargo.toml").exists():
            return []
        return [
            TestCommandCandidate(
                command="cargo test",
                tool="cargo",
                reason="Cargo.toml detected.",
                confidence="high",
            ),
            TestCommandCandidate(
                command="cargo check",
                tool="cargo",
                reason="Cargo.toml detected.",
                confidence="medium",
            ),
        ]


def _dedupe_commands(candidates: list[TestCommandCandidate]) -> list[TestCommandCandidate]:
    seen: set[str] = set()
    deduped: list[TestCommandCandidate] = []
    for candidate in candidates:
        if candidate.command in seen:
            continue
        seen.add(candidate.command)
        deduped.append(candidate)
    return deduped
