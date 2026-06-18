"""Run id validation helpers."""

from __future__ import annotations

import re
import secrets

from safecode.enterprise.workflow.exceptions import InvalidRunIdError

_RUN_ID_RE = re.compile(r"^run-[a-zA-Z0-9_-]{8,64}$")


def generate_run_id() -> str:
    return f"run-{secrets.token_hex(6)}"


def validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not _RUN_ID_RE.match(run_id):
        raise InvalidRunIdError(f"invalid run_id: {run_id!r}")
    if ".." in run_id or "/" in run_id or "\\" in run_id:
        raise InvalidRunIdError(f"invalid run_id path characters: {run_id!r}")
    return run_id
