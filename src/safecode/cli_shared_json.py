"""Shared JSON output rendering for daily CLI commands."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


class CLIJSONResponse(BaseModel):
    """Structured JSON response for CLI commands."""

    command: str
    status: str  # "success", "error", "pass", "fail"
    data: dict[str, Any] = {}
    error: str | None = None


def render_json(response: CLIJSONResponse) -> str:
    """Return a deterministic, sorted-keys JSON string for the response.

    Null ``error`` is omitted so callers can check ``"error" in json.loads(output)``.
    """
    payload: dict[str, Any] = {
        "command": response.command,
        "status": response.status,
        "data": response.data,
    }
    if response.error is not None:
        payload["error"] = response.error
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
