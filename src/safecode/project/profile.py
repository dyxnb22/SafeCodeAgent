"""Project command profile detector and persistence (v4.2, EXPERIMENTAL).

Detects test/lint/typecheck/build commands for Python, Node, Go, and Rust projects.
Persists to .sac/project_profile.json atomically. User overrides survive detect.
"""

from __future__ import annotations

import json
import os
import shutil
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

_PROFILE_FILENAME = "project_profile.json"
_SHELL_METACHAR = frozenset(";|&$`\n")

_VALID_KINDS = frozenset({"test", "lint", "typecheck", "build"})


def _has_metachar(s: str) -> bool:
    return any(c in _SHELL_METACHAR for c in s)


class ProfileCommand(BaseModel):
    """A detected or user-configured command for one profile kind."""

    model_config = {"frozen": True}

    command: tuple[str, ...]
    stack: str
    source: Literal["detected", "user", "none"]
    missing_dependency: bool = False


class ProjectProfile(BaseModel):
    """Project command profile. All four kinds may be None if not detected."""

    model_config = {"frozen": True}

    payload_version: int = 1
    test: ProfileCommand | None = None
    lint: ProfileCommand | None = None
    typecheck: ProfileCommand | None = None
    build: ProfileCommand | None = None
    user_overrides: frozenset[str] = frozenset()


def _profile_path(project_root: Path) -> Path:
    return project_root / ".sac" / _PROFILE_FILENAME


def load_profile(project_root: Path) -> ProjectProfile | None:
    """Load profile from disk. Returns None if missing or unparseable."""
    path = _profile_path(project_root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ProjectProfile.model_validate(data)
    except Exception:
        return None


def save_profile(project_root: Path, profile: ProjectProfile) -> None:
    """Atomically persist the profile to .sac/project_profile.json."""
    sac_dir = project_root / ".sac"
    sac_dir.mkdir(parents=True, exist_ok=True)
    target = _profile_path(project_root)
    tmp = target.with_suffix(".tmp")

    data = profile.model_dump(mode="json")
    # Ensure frozenset serialises deterministically
    data["user_overrides"] = sorted(profile.user_overrides)
    # Tuples become lists in model_dump; that is acceptable for round-trip

    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, target)


# ---------------------------------------------------------------------------
# Internal detection helpers
# ---------------------------------------------------------------------------


def _tool_missing(argv: tuple[str, ...]) -> bool:
    """Return True when the head binary is not found on PATH."""
    return shutil.which(argv[0]) is None


def _cmd(argv: tuple[str, ...], stack: str, source: str = "detected") -> ProfileCommand:
    return ProfileCommand(
        command=argv,
        stack=stack,
        source=source,  # type: ignore[arg-type]
        missing_dependency=_tool_missing(argv),
    )


def _is_python_project(root: Path) -> bool:
    return (
        (root / "pyproject.toml").exists()
        or (root / "setup.py").exists()
        or (root / "pytest.ini").exists()
        or (root / "setup.cfg").exists()
        or (root / "tests").is_dir()
    )


def _is_node_project(root: Path) -> bool:
    return (root / "package.json").exists()


def _is_go_project(root: Path) -> bool:
    return (root / "go.mod").exists()


def _is_rust_project(root: Path) -> bool:
    return (root / "Cargo.toml").exists()


def _detect_python_commands(root: Path) -> dict[str, ProfileCommand]:
    out: dict[str, ProfileCommand] = {}
    if (root / "uv.lock").exists():
        out["test"] = _cmd(("uv", "run", "pytest", "-q"), "python")
    else:
        out["test"] = _cmd(("pytest", "-q"), "python")
    out["lint"] = _cmd(("ruff", "check", "."), "python")
    out["typecheck"] = _cmd(("mypy", "."), "python")
    # No build command for Python
    return out


def _node_tool(root: Path) -> str:
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    return "npm"


def _detect_node_commands(root: Path) -> dict[str, ProfileCommand]:
    package_json = root / "package.json"
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = data.get("scripts", {})
    if not isinstance(scripts, dict):
        return {}

    tool = _node_tool(root)
    out: dict[str, ProfileCommand] = {}
    for kind, script_name in (
        ("test", "test"),
        ("lint", "lint"),
        ("typecheck", "typecheck"),
        ("build", "build"),
    ):
        if script_name not in scripts:
            continue
        if script_name == "test" and tool in {"npm", "pnpm"}:
            argv: tuple[str, ...] = (tool, "test")
        elif script_name == "test" and tool == "yarn":
            argv = ("yarn", "test")
        elif tool == "yarn":
            argv = ("yarn", script_name)
        else:
            argv = (tool, "run", script_name)
        out[kind] = _cmd(argv, "node")
    return out


def _detect_go_commands(root: Path) -> dict[str, ProfileCommand]:
    return {
        "test": _cmd(("go", "test", "./..."), "go"),
        "lint": _cmd(("go", "vet", "./..."), "go"),
        # No typecheck for Go (go vet covers static analysis)
        "build": _cmd(("go", "build", "./..."), "go"),
    }


def _detect_rust_commands(root: Path) -> dict[str, ProfileCommand]:
    return {
        "test": _cmd(("cargo", "test"), "rust"),
        "lint": _cmd(("cargo", "clippy", "--no-deps"), "rust"),
        "typecheck": _cmd(("cargo", "check"), "rust"),
        "build": _cmd(("cargo", "build"), "rust"),
    }


def _detect_raw(root: Path) -> dict[str, ProfileCommand]:
    """Return detected commands (no user override applied)."""
    if _is_python_project(root):
        return _detect_python_commands(root)
    if _is_node_project(root):
        return _detect_node_commands(root)
    if _is_go_project(root):
        return _detect_go_commands(root)
    if _is_rust_project(root):
        return _detect_rust_commands(root)
    return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_profile(project_root: Path) -> ProjectProfile:
    """Detect project commands, re-apply user overrides, and return the new profile.

    User overrides always win; they are never cleared by detection.
    Detection never executes project commands.
    """
    existing = load_profile(project_root)
    user_overrides: frozenset[str] = existing.user_overrides if existing else frozenset()

    detected = _detect_raw(project_root)

    # Start with detected commands for all kinds
    merged: dict[str, ProfileCommand | None] = {
        "test": detected.get("test"),
        "lint": detected.get("lint"),
        "typecheck": detected.get("typecheck"),
        "build": detected.get("build"),
    }

    # Re-apply any user overrides that are still set
    if existing:
        for kind in _VALID_KINDS:
            if kind in user_overrides:
                existing_cmd = getattr(existing, kind)
                if existing_cmd is not None and existing_cmd.source == "user":
                    merged[kind] = existing_cmd

    return ProjectProfile(
        payload_version=1,
        test=merged["test"],
        lint=merged["lint"],
        typecheck=merged["typecheck"],
        build=merged["build"],
        user_overrides=user_overrides,
    )


def apply_user_override(
    project_root: Path,
    kind: str,
    argv: tuple[str, ...],
) -> ProjectProfile:
    """Set a user override for the given kind and persist. Returns updated profile."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"Unknown kind: {kind!r}. Must be one of: {sorted(_VALID_KINDS)}")

    profile = load_profile(project_root) or ProjectProfile()
    override_cmd = ProfileCommand(
        command=argv,
        stack="user",
        source="user",
        missing_dependency=_tool_missing(argv),
    )
    updated = profile.model_copy(update={
        kind: override_cmd,
        "user_overrides": profile.user_overrides | {kind},
    })
    save_profile(project_root, updated)
    return updated


def clear_user_override(project_root: Path, kind: str) -> ProjectProfile:
    """Clear the user override for the given kind and re-detect from project."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"Unknown kind: {kind!r}. Must be one of: {sorted(_VALID_KINDS)}")

    profile = load_profile(project_root) or ProjectProfile()
    detected = _detect_raw(project_root)
    updated = profile.model_copy(update={
        kind: detected.get(kind),
        "user_overrides": profile.user_overrides - {kind},
    })
    save_profile(project_root, updated)
    return updated
