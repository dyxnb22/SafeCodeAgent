"""Stdio JSON-RPC 2.0 bridge exposing SafeCodeLocalAPI (experimental).

EXPERIMENTAL: this surface is not a stable public contract.

Only ask, report, edit, and apply are exposed. Writes remain gated by
the existing pending-patch safety machinery (checkpoint + audit).
Transport: newline-delimited JSON over stdin/stdout (stdio).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import IO, Any

from safecode.agent.orchestrator import AgentOrchestrator
from safecode.report.render import ReportRenderer

_JSONRPC_VERSION = "2.0"
_SUPPORTED_METHODS = frozenset({"ask", "report", "edit", "apply"})

CONTRACT_VERSION = "1"


class _JsonRpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _ok(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": _JSONRPC_VERSION, "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": _JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _dispatch(method: str, params: dict, project_root: Path) -> Any:
    """Dispatch a JSON-RPC method to the appropriate LocalAPI method.

    Error text never contains caller-supplied params content.
    """
    if method == "ask":
        question = params.get("question")
        if not isinstance(question, str) or not question:
            raise _JsonRpcError(-32602, "Invalid params: question string required")
        orch = AgentOrchestrator(project_root)
        answer = orch.ask(question)
        return {"answer": answer}

    if method == "report":
        report = ReportRenderer(project_root).render_markdown()
        return {"report": report}

    if method == "edit":
        task = params.get("task")
        if not isinstance(task, str) or not task:
            raise _JsonRpcError(-32602, "Invalid params: task string required")
        orch = AgentOrchestrator(project_root)
        result = orch.edit(task)
        return {
            "patch_id": result.proposal.id,
            "status": result.proposal.status,
            "diff": result.diff_text,
            "pending_patch_path": str(result.pending_patch_path),
        }

    if method == "apply":
        orch = AgentOrchestrator(project_root)
        preview = orch.preview_apply()
        result = orch.apply(preview.proposal)
        return {
            "patch_id": result.proposal.id,
            "files": result.files,
            "checkpoint_id": result.checkpoint.id,
        }

    raise _JsonRpcError(-32601, "Method not found")


def process_request(line: str, project_root: Path) -> dict:
    """Parse and dispatch one JSON-RPC request line. Never raises."""
    request_id: Any = None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return _err(None, -32700, "Parse error")

    if not isinstance(data, dict):
        return _err(None, -32600, "Invalid Request")

    request_id = data.get("id")

    if data.get("jsonrpc") != _JSONRPC_VERSION:
        return _err(request_id, -32600, "Invalid Request: jsonrpc 2.0 required")

    method = data.get("method", "")
    if not isinstance(method, str) or not method:
        return _err(request_id, -32600, "Invalid Request: method required")

    if method not in _SUPPORTED_METHODS:
        return _err(request_id, -32601, "Method not found")

    params = data.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    try:
        result = _dispatch(method, params, project_root)
        return _ok(request_id, result)
    except _JsonRpcError as e:
        return _err(request_id, e.code, e.message)
    except FileNotFoundError:
        return _err(request_id, -32603, "Internal error: resource not found")
    except Exception:
        return _err(request_id, -32603, "Internal error")


def run_server(
    project_root: Path,
    *,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
) -> None:
    """Run the JSON-RPC server loop until EOF.

    Reads newline-delimited JSON from *stdin* and writes responses to *stdout*.
    Designed to be launched as a subprocess by an IDE extension.
    """
    if stdin is None:
        stdin = sys.stdin
    if stdout is None:
        stdout = sys.stdout

    for line in stdin:
        stripped = line.strip()
        if not stripped:
            continue
        response = process_request(stripped, project_root)
        stdout.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
        stdout.flush()
