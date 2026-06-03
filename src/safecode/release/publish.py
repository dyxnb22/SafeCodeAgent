"""Release publish: dry-run report or real build/sign/upload."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from safecode.release.version_guard import check_tag_consistency, check_version_consistency

_REQUIRED_ENV = "SAFECODE_PUBLISH"
_DIST_DIR = "dist"


@dataclass(frozen=True)
class PublishResult:
    """Result of sac release publish."""

    dry_run: bool
    ok: bool
    steps: tuple[str, ...]
    errors: tuple[str, ...]


def _planned_steps(*, sign: bool) -> list[str]:
    steps = [f"build: uv build → {_DIST_DIR}/"]
    if sign:
        steps.append("sign: sign distribution artifacts (cosign or gpg)")
    steps.append("upload: uv publish dist/*")
    return steps


def _check_sign_tooling() -> str | None:
    """Return None if signing tooling is available, else an error message."""
    if shutil.which("cosign") is not None:
        return None
    if shutil.which("gpg") is not None:
        return None
    return (
        "signing requested but no signing tool found (cosign or gpg); "
        "install a signing tool or omit --sign"
    )


def run_release_publish(
    project_root: Path | None = None,
    *,
    dry_run: bool = False,
    sign: bool = False,
) -> PublishResult:
    """Run or simulate release publish.

    Dry-run: deterministic — describes planned steps, executes nothing.
    Real publish: requires SAFECODE_PUBLISH=1 and a clean matching git tag.
    Sign: requires cosign or gpg; fails closed if neither is found.
    """
    from safecode import __version__

    root = project_root or Path.cwd()
    steps = _planned_steps(sign=sign)

    if dry_run:
        dry_steps = tuple(f"[dry-run] {s}" for s in steps)
        return PublishResult(dry_run=True, ok=True, steps=dry_steps, errors=())

    errors: list[str] = []

    # Gate 1: explicit publish intent
    if not os.getenv(_REQUIRED_ENV):
        errors.append(
            f"real publish requires {_REQUIRED_ENV}=1; "
            "set it to confirm intentional publish"
        )
        return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors))

    # Gate 2: version consistency
    version_result = check_version_consistency(
        pyproject_path=root / "pyproject.toml",
        runtime_version=__version__,
    )
    if not version_result.ok:
        errors.append(f"version inconsistency: {version_result.message}")
        return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors))

    version = version_result.package_version

    # Gate 3: clean matching git tag at HEAD
    tag_result = check_tag_consistency(version, project_root=root)
    if not tag_result.consistent:
        errors.append(f"tag check failed: {tag_result.message}")
        return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors))

    # Gate 4: signing tooling availability (if requested)
    if sign:
        sign_error = _check_sign_tooling()
        if sign_error:
            errors.append(sign_error)
            return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors))

    # Execute: build
    dist_dir = root / _DIST_DIR
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    build_proc = subprocess.run(
        ["uv", "build"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if build_proc.returncode != 0:
        errors.append(f"build failed (exit {build_proc.returncode})")
        return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors))

    # Execute: sign
    if sign:
        tool = "cosign" if shutil.which("cosign") else "gpg"
        for artifact in sorted(dist_dir.glob("*")):
            if tool == "cosign":
                sign_cmd = ["cosign", "sign-blob", "--yes", str(artifact)]
            else:
                sign_cmd = ["gpg", "--detach-sign", "--armor", str(artifact)]
            sign_proc = subprocess.run(sign_cmd, capture_output=True, text=True)
            if sign_proc.returncode != 0:
                errors.append(
                    f"signing failed for {artifact.name} (exit {sign_proc.returncode})"
                )
                return PublishResult(
                    dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors)
                )

    # Execute: upload
    upload_proc = subprocess.run(
        ["uv", "publish"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if upload_proc.returncode != 0:
        errors.append(f"upload failed (exit {upload_proc.returncode})")
        return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors))

    return PublishResult(dry_run=False, ok=True, steps=tuple(steps), errors=())


def render_publish_result(result: PublishResult) -> str:
    """Render a publish result for human-readable CLI output."""
    mode = "dry-run" if result.dry_run else "live"
    status = "PASS" if result.ok else "FAIL"
    lines = [f"SafeCode Release Publish [{status}] ({mode})", ""]
    if result.steps:
        lines.append("Steps:")
        for step in result.steps:
            lines.append(f"  {step}")
    if result.errors:
        lines.append("")
        lines.append("Errors:")
        for error in result.errors:
            lines.append(f"  {error}")
    if result.ok and not result.dry_run:
        lines.extend(["", "Published successfully."])
    return "\n".join(lines)
