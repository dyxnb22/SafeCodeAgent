#!/usr/bin/env python3
"""Safely extract a validated Enterprise backup archive."""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path, PurePosixPath


def _validate_member(member: tarfile.TarInfo, destination: Path) -> None:
    name = PurePosixPath(member.name)
    if name.is_absolute() or ".." in name.parts:
        raise ValueError(f"unsafe archive member path: {member.name}")
    target = (destination / Path(*name.parts)).resolve()
    if destination != target and destination not in target.parents:
        raise ValueError(f"archive member escapes destination: {member.name}")
    if member.issym() or member.islnk() or member.isdev() or member.isfifo():
        raise ValueError(f"unsupported archive member type: {member.name}")


def extract_validated(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, mode="r:gz") as bundle:
        members = bundle.getmembers()
        for member in members:
            _validate_member(member, root)
        bundle.extractall(root, members=members)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    extract_validated(args.archive, args.destination)


if __name__ == "__main__":
    main()
