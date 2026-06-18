#!/usr/bin/env python3
"""Verify packaging inputs and, when available, build artifacts."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SOURCE_FILES = [
    "src/safecode/shell/runtime.py",
    "src/safecode/shell/session.py",
    "src/safecode/shell/approvals.py",
    "src/safecode/shell/rendering.py",
    "src/safecode/memory/ledger.py",
    "docs/architecture.md",
    "docs/demo/claude-style-session.md",
    "CHANGELOG.md",
]

REQUIRED_SDIST_MEMBERS = [
    "README.md",
    "CHANGELOG.md",
    "docs/architecture.md",
    "docs/demo/claude-style-session.md",
    "src/safecode/shell/runtime.py",
    "src/safecode/memory/ledger.py",
]

REQUIRED_WHEEL_MEMBERS = [
    "safecode/shell/runtime.py",
    "safecode/shell/session.py",
    "safecode/shell/approvals.py",
    "safecode/memory/ledger.py",
]


def _fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def _check_source_files() -> int:
    missing = [path for path in REQUIRED_SOURCE_FILES if not (ROOT / path).exists()]
    if missing:
        return _fail("missing package inputs: " + ", ".join(missing))
    return 0


def _check_build_module() -> bool:
    return importlib.util.find_spec("build") is not None


def _run_build(dist_dir: Path) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(dist_dir)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(result.stdout)
    return result.returncode


def _member_exists(members: list[str], suffix: str) -> bool:
    return any(member.endswith(suffix) for member in members)


def _check_sdist(sdist: Path) -> int:
    with tarfile.open(sdist, "r:gz") as archive:
        members = archive.getnames()
    missing = [item for item in REQUIRED_SDIST_MEMBERS if not _member_exists(members, item)]
    if missing:
        return _fail("sdist missing: " + ", ".join(missing))
    return 0


def _check_wheel(wheel: Path) -> int:
    with zipfile.ZipFile(wheel) as archive:
        members = archive.namelist()
    missing = [item for item in REQUIRED_WHEEL_MEMBERS if item not in members]
    if missing:
        return _fail("wheel missing: " + ", ".join(missing))
    return 0


def main() -> int:
    source_code = _check_source_files()
    if source_code:
        return source_code

    if not _check_build_module():
        print("OK: package inputs present; python module 'build' is not installed, skipping artifact build.")
        print("Next: python3 -m pip install build && python3 scripts/verify-package.py")
        return 0

    with tempfile.TemporaryDirectory(prefix="safecode-dist-") as tmp:
        dist_dir = Path(tmp)
        build_code = _run_build(dist_dir)
        if build_code:
            return build_code
        sdists = sorted(dist_dir.glob("*.tar.gz"))
        wheels = sorted(dist_dir.glob("*.whl"))
        if not sdists:
            return _fail("no sdist produced")
        if not wheels:
            return _fail("no wheel produced")
        sdist_code = _check_sdist(sdists[-1])
        if sdist_code:
            return sdist_code
        wheel_code = _check_wheel(wheels[-1])
        if wheel_code:
            return wheel_code

    print("OK: package source inputs, sdist, and wheel contents verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
