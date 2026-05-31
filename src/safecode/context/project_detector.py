"""Detect coarse project type from common manifest files."""


def detect_project_type(files: list[str]) -> str:
    """Return a rough project type label."""
    normalized = {path.replace("\\", "/") for path in files}
    if "pyproject.toml" in normalized:
        if any(path.startswith("app/") or path.startswith("src/") for path in normalized):
            return "python"
        return "python-package"
    if "package.json" in normalized:
        return "node"
    if "Cargo.toml" in normalized:
        return "rust"
    if "go.mod" in normalized:
        return "go"
    if "pom.xml" in normalized:
        return "maven"
    if normalized & {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}:
        return "gradle"
    return "unknown"
