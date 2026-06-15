"""GitHub read-only native tools via the `gh` CLI (v4.24.1+, EXPERIMENTAL).

Tools: github_read_issue, github_read_pr, github_read_file

Safety invariants:
- All subprocess calls use argv lists (shell=False always). No shell injection possible.
- owner/repo inputs validated against a safe pattern to prevent argument injection.
- Requires network_enabled=True; blocked by default.
- `gh` binary must be available; missing gh → blocked NativeToolResult.
- Outputs redacted via redact_secrets() before returning.
- Auth via GITHUB_TOKEN env var or `gh auth status` — never written to disk.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolResult, NativeToolSpec
from safecode.config import SafeCodeConfig
from safecode.context.redactor import redact_secrets

# Safe identifier pattern for owner/repo names.
_SAFE_GH_NAME = re.compile(r"^[a-zA-Z0-9._-]{1,100}$")
_GH_TIMEOUT = 30  # seconds


def _validate_gh_name(value: str, field: str) -> str | None:
    """Return error message if value is not a safe GitHub owner or repo name."""
    if not value or not _SAFE_GH_NAME.match(value):
        return f"Invalid {field}: must match [a-zA-Z0-9._-]+ (got {value!r})"
    return None


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _run_gh(args: list[str]) -> tuple[bool, str]:
    """Run `gh <args>` and return (success, output_or_error)."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT,
        )
        if result.returncode == 0:
            return True, result.stdout
        return False, result.stderr or f"gh exited {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, f"gh command timed out after {_GH_TIMEOUT}s"
    except FileNotFoundError:
        return False, "gh CLI not found; install GitHub CLI (https://cli.github.com)"
    except Exception as exc:
        return False, f"gh command failed: {type(exc).__name__}"


def _network_check(project_root: Path) -> str | None:
    """Return error string if network is disabled; None if allowed."""
    config = SafeCodeConfig.load(project_root)
    if not getattr(config.sandbox, "network_enabled", False):
        return "GitHub tools require network: true in config (disabled by default)."
    return None


# ---------------------------------------------------------------------------
# github_read_issue
# ---------------------------------------------------------------------------

def _read_issue_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    owner: str = inp.get("owner", "").strip()
    repo: str = inp.get("repo", "").strip()
    issue: int | str = inp.get("issue", 0)

    net_err = _network_check(project_root)
    if net_err:
        return NativeToolResult(call_id=call_id, tool_name="github_read_issue", status="blocked", error=net_err)

    if not _gh_available():
        return NativeToolResult(call_id=call_id, tool_name="github_read_issue", status="blocked",
                                error="gh CLI not found; install GitHub CLI.")

    for field, val in (("owner", owner), ("repo", repo)):
        err = _validate_gh_name(val, field)
        if err:
            return NativeToolResult(call_id=call_id, tool_name="github_read_issue", status="error", error=err)

    try:
        issue_num = int(issue)
        if issue_num <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return NativeToolResult(call_id=call_id, tool_name="github_read_issue", status="error",
                                error=f"Invalid issue number: {issue!r}")

    ok, output = _run_gh([
        "issue", "view", str(issue_num),
        "--repo", f"{owner}/{repo}",
        "--json", "title,body,labels,state,number",
    ])
    if not ok:
        return NativeToolResult(call_id=call_id, tool_name="github_read_issue", status="error", error=output)

    return NativeToolResult(
        call_id=call_id, tool_name="github_read_issue", status="success",
        output=redact_secrets(output),
        metadata={"owner": owner, "repo": repo, "issue": issue_num},
    )


GITHUB_READ_ISSUE_SPEC = NativeToolSpec(
    name="github_read_issue",
    description="Read a GitHub issue (title, body, labels, state) via gh CLI. Requires network: true.",
    input_schema={
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "GitHub repository owner (username or org)."},
            "repo": {"type": "string", "description": "GitHub repository name."},
            "issue": {"type": "integer", "description": "Issue number."},
        },
        "required": ["owner", "repo", "issue"],
    },
    requires_approval=False,
    audit_event_type="tool_call_read",
)


# ---------------------------------------------------------------------------
# github_read_pr
# ---------------------------------------------------------------------------

def _read_pr_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    owner: str = inp.get("owner", "").strip()
    repo: str = inp.get("repo", "").strip()
    pr: int | str = inp.get("pr", 0)

    net_err = _network_check(project_root)
    if net_err:
        return NativeToolResult(call_id=call_id, tool_name="github_read_pr", status="blocked", error=net_err)

    if not _gh_available():
        return NativeToolResult(call_id=call_id, tool_name="github_read_pr", status="blocked",
                                error="gh CLI not found; install GitHub CLI.")

    for field, val in (("owner", owner), ("repo", repo)):
        err = _validate_gh_name(val, field)
        if err:
            return NativeToolResult(call_id=call_id, tool_name="github_read_pr", status="error", error=err)

    try:
        pr_num = int(pr)
        if pr_num <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return NativeToolResult(call_id=call_id, tool_name="github_read_pr", status="error",
                                error=f"Invalid PR number: {pr!r}")

    ok, output = _run_gh([
        "pr", "view", str(pr_num),
        "--repo", f"{owner}/{repo}",
        "--json", "title,body,state,reviewDecision,headRefName,baseRefName,number",
    ])
    if not ok:
        return NativeToolResult(call_id=call_id, tool_name="github_read_pr", status="error", error=output)

    return NativeToolResult(
        call_id=call_id, tool_name="github_read_pr", status="success",
        output=redact_secrets(output),
        metadata={"owner": owner, "repo": repo, "pr": pr_num},
    )


GITHUB_READ_PR_SPEC = NativeToolSpec(
    name="github_read_pr",
    description="Read a GitHub pull request (title, body, state, review status) via gh CLI. Requires network: true.",
    input_schema={
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "GitHub repository owner."},
            "repo": {"type": "string", "description": "GitHub repository name."},
            "pr": {"type": "integer", "description": "Pull request number."},
        },
        "required": ["owner", "repo", "pr"],
    },
    requires_approval=False,
    audit_event_type="tool_call_read",
)


# ---------------------------------------------------------------------------
# github_read_file
# ---------------------------------------------------------------------------

def _read_file_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    owner: str = inp.get("owner", "").strip()
    repo: str = inp.get("repo", "").strip()
    path: str = inp.get("path", "").strip()
    ref: str = inp.get("ref", "").strip()

    net_err = _network_check(project_root)
    if net_err:
        return NativeToolResult(call_id=call_id, tool_name="github_read_file", status="blocked", error=net_err)

    if not _gh_available():
        return NativeToolResult(call_id=call_id, tool_name="github_read_file", status="blocked",
                                error="gh CLI not found; install GitHub CLI.")

    for field, val in (("owner", owner), ("repo", repo)):
        err = _validate_gh_name(val, field)
        if err:
            return NativeToolResult(call_id=call_id, tool_name="github_read_file", status="error", error=err)

    if not path:
        return NativeToolResult(call_id=call_id, tool_name="github_read_file", status="error",
                                error="Missing 'path' input.")
    if ".." in path:
        return NativeToolResult(call_id=call_id, tool_name="github_read_file", status="blocked",
                                error="Path traversal '..' is not allowed.")

    api_path = f"repos/{owner}/{repo}/contents/{path.lstrip('/')}"
    args = ["api", api_path]
    if ref:
        args += ["--field", f"ref={ref}"]

    ok, output = _run_gh(args)
    if not ok:
        return NativeToolResult(call_id=call_id, tool_name="github_read_file", status="error", error=output)

    try:
        data = json.loads(output)
        encoded = data.get("content", "")
        if not encoded:
            return NativeToolResult(call_id=call_id, tool_name="github_read_file", status="error",
                                    error="Response has no 'content' field (may be a directory or large file).")
        decoded = base64.b64decode(encoded.replace("\n", "")).decode("utf-8", errors="replace")
        decoded = redact_secrets(decoded)
        return NativeToolResult(
            call_id=call_id, tool_name="github_read_file", status="success",
            output=decoded,
            metadata={"owner": owner, "repo": repo, "path": path, "ref": ref or "default"},
        )
    except (json.JSONDecodeError, Exception) as exc:
        return NativeToolResult(call_id=call_id, tool_name="github_read_file", status="error",
                                error=f"Failed to decode response: {type(exc).__name__}")


GITHUB_READ_FILE_SPEC = NativeToolSpec(
    name="github_read_file",
    description="Read a file from a GitHub repository at a given ref via gh CLI. Requires network: true.",
    input_schema={
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "GitHub repository owner."},
            "repo": {"type": "string", "description": "GitHub repository name."},
            "path": {"type": "string", "description": "File path within the repository."},
            "ref": {"type": "string", "description": "Branch, tag, or commit SHA (optional; defaults to repo default branch)."},
        },
        "required": ["owner", "repo", "path"],
    },
    requires_approval=False,
    audit_event_type="tool_call_read",
)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_github_read_tools(dispatcher: NativeToolDispatcher, project_root: Path) -> None:
    """Register all three GitHub read tools on a dispatcher, injecting project_root."""

    def _issue_handler(call_id: str, inp: dict) -> NativeToolResult:
        return _read_issue_handler(call_id, {"_project_root": str(project_root), **inp})

    def _pr_handler(call_id: str, inp: dict) -> NativeToolResult:
        return _read_pr_handler(call_id, {"_project_root": str(project_root), **inp})

    def _file_handler(call_id: str, inp: dict) -> NativeToolResult:
        return _read_file_handler(call_id, {"_project_root": str(project_root), **inp})

    dispatcher.register(GITHUB_READ_ISSUE_SPEC, _issue_handler)
    dispatcher.register(GITHUB_READ_PR_SPEC, _pr_handler)
    dispatcher.register(GITHUB_READ_FILE_SPEC, _file_handler)
