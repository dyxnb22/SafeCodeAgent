"""Release publish: dry-run report or real build/sign/upload.

Signing mechanism: detached signature via cosign or gpg.
  - cosign: `cosign sign-blob --yes <artifact>` (keyless or key-based per env)
  - gpg: `gpg --detach-sign --armor <artifact>`
No Sigstore transparency log is required; the detached signature file is
placed alongside each artifact in dist/. This is the only supported signing
mechanism; --sign is not Sigstore-in-rekor.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from safecode.release.version_guard import check_tag_consistency, check_version_consistency

_REQUIRED_ENV = "SAFECODE_PUBLISH"
_DIST_DIR = "dist"

# Supported repository targets and their upload URLs.
_REPOSITORY_URLS: dict[str, str] = {
    "pypi": "https://upload.pypi.org/legacy/",
    "test-pypi": "https://test.pypi.org/legacy/",
}


@dataclass(frozen=True)
class PublishResult:
    """Result of sac release publish."""

    dry_run: bool
    ok: bool
    steps: tuple[str, ...]
    errors: tuple[str, ...]
    repository: str = "pypi"


def _planned_steps(*, sign: bool, repository: str = "pypi") -> list[str]:
    repo_label = f" (→ {repository})" if repository != "pypi" else ""
    steps = [f"build: uv build → {_DIST_DIR}/"]
    if sign:
        steps.append(
            "sign: detached signature via cosign (sign-blob) or gpg (--detach-sign --armor)"
        )
    steps.append(f"upload: uv publish dist/*{repo_label}")
    return steps


def _check_sign_tooling() -> str | None:
    """Return None if signing tooling is available, else an error message."""
    if shutil.which("cosign") is not None:
        return None
    if shutil.which("gpg") is not None:
        return None
    return (
        "signing requested but no signing tool found (cosign or gpg); "
        "install cosign or gpg, or omit --sign. "
        "Note: --sign produces a detached signature (cosign sign-blob or gpg --detach-sign), "
        "not a Sigstore transparency-log entry."
    )


def run_release_publish(
    project_root: Path | None = None,
    *,
    dry_run: bool = False,
    sign: bool = False,
    repository: str = "pypi",
) -> PublishResult:
    """Run or simulate release publish.

    Dry-run: deterministic — describes planned steps, executes nothing.
    Real publish: requires SAFECODE_PUBLISH=1 and a clean matching git tag.
    Sign: produces a detached cosign or gpg signature for each artifact;
          fails closed if neither tool is found.
    Repository: 'pypi' (default) or 'test-pypi' for TestPyPI rehearsal.
    """
    from safecode import __version__

    if repository not in _REPOSITORY_URLS:
        known = ", ".join(sorted(_REPOSITORY_URLS))
        return PublishResult(
            dry_run=dry_run,
            ok=False,
            steps=(),
            errors=(f"unknown repository {repository!r}; known: {known}",),
            repository=repository,
        )

    root = project_root or Path.cwd()
    steps = _planned_steps(sign=sign, repository=repository)

    if dry_run:
        dry_steps = tuple(f"[dry-run] {s}" for s in steps)
        return PublishResult(dry_run=True, ok=True, steps=dry_steps, errors=(), repository=repository)

    errors: list[str] = []

    # Gate 1: explicit publish intent (required for both pypi and test-pypi)
    if not os.getenv(_REQUIRED_ENV):
        errors.append(
            f"real publish requires {_REQUIRED_ENV}=1; "
            "set it to confirm intentional publish"
        )
        return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors), repository=repository)

    # Gate 2: version consistency
    version_result = check_version_consistency(
        pyproject_path=root / "pyproject.toml",
        runtime_version=__version__,
    )
    if not version_result.ok:
        errors.append(f"version inconsistency: {version_result.message}")
        return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors), repository=repository)

    version = version_result.package_version

    # Gate 3: clean matching git tag at HEAD
    tag_result = check_tag_consistency(version, project_root=root)
    if not tag_result.consistent:
        errors.append(f"tag check failed: {tag_result.message}")
        return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors), repository=repository)

    # Gate 4: signing tooling availability (if requested)
    if sign:
        sign_error = _check_sign_tooling()
        if sign_error:
            errors.append(sign_error)
            return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors), repository=repository)

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
        return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors), repository=repository)

    # Execute: sign (detached signature only)
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
                    dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors), repository=repository
                )

    # Execute: upload
    upload_url = _REPOSITORY_URLS[repository]
    upload_proc = subprocess.run(
        ["uv", "publish", "--publish-url", upload_url],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if upload_proc.returncode != 0:
        errors.append(f"upload failed (exit {upload_proc.returncode})")
        return PublishResult(dry_run=False, ok=False, steps=tuple(steps), errors=tuple(errors), repository=repository)

    return PublishResult(dry_run=False, ok=True, steps=tuple(steps), errors=(), repository=repository)


def render_publish_result(result: PublishResult) -> str:
    """Render a publish result for human-readable CLI output."""
    mode = "dry-run" if result.dry_run else "live"
    repo = result.repository if result.repository != "pypi" else "pypi"
    status = "PASS" if result.ok else "FAIL"
    lines = [f"SafeCode Release Publish [{status}] ({mode}, repository={repo})", ""]
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
