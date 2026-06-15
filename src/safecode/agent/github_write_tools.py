"""GitHub write native tools via `gh` CLI and `git` (v4.24.2+, EXPERIMENTAL).

Tools: github_create_pr, github_push_branch

Safety invariants:
- Both tools require requires_approval=True — always paused for user approval.
- All subprocess calls use shell=False argv lists; no shell injection.
- owner/repo and branch names validated against safe patterns.
- github_push_branch with force=True requires explicit force flag in input
  (double-safeguard against accidental force pushes).
- Requires network_enabled=True; blocked by default.
- Never stores credentials; uses GITHUB_TOKEN env or gh auth status.
- Outputs redacted via redact_secrets().
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from safecode.agent.github_read_tools import _gh_available, _network_check, _run_gh, _validate_gh_name
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolResult, NativeToolSpec
from safecode.context.redactor import redact_secrets

_SAFE_BRANCH = re.compile(r"^[a-zA-Z0-9._/-]{1,200}$")
_GH_TIMEOUT = 30


def _validate_branch(name: str) -> str | None:
    if not name or not _SAFE_BRANCH.match(name):
        return f"Invalid branch name: {name!r}"
    if name.startswith("-"):
        return f"Branch name must not start with '-': {name!r}"
    return None


# ---------------------------------------------------------------------------
# github_create_pr
# ---------------------------------------------------------------------------

def _create_pr_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    title: str = inp.get("title", "").strip()
    body: str = inp.get("body", "").strip()
    base: str = inp.get("base", "").strip()
    draft: bool = bool(inp.get("draft", False))

    net_err = _network_check(project_root)
    if net_err:
        return NativeToolResult(call_id=call_id, tool_name="github_create_pr", status="blocked", error=net_err)

    if not _gh_available():
        return NativeToolResult(call_id=call_id, tool_name="github_create_pr", status="blocked",
                                error="gh CLI not found; install GitHub CLI.")

    if not title:
        return NativeToolResult(call_id=call_id, tool_name="github_create_pr", status="error",
                                error="Missing 'title' input.")

    args = ["pr", "create", "--title", title, "--body", body]
    if base:
        err = _validate_branch(base)
        if err:
            return NativeToolResult(call_id=call_id, tool_name="github_create_pr", status="error", error=err)
        args += ["--base", base]
    if draft:
        args.append("--draft")

    ok, output = _run_gh(args)
    if not ok:
        return NativeToolResult(call_id=call_id, tool_name="github_create_pr", status="error",
                                error=redact_secrets(output))

    pr_url = output.strip()
    return NativeToolResult(
        call_id=call_id, tool_name="github_create_pr", status="success",
        output=redact_secrets(pr_url),
        metadata={"pr_url": pr_url, "draft": draft},
    )


GITHUB_CREATE_PR_SPEC = NativeToolSpec(
    name="github_create_pr",
    description=(
        "Create a GitHub pull request via gh CLI. Approval required. "
        "Requires network: true."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "PR title."},
            "body": {"type": "string", "description": "PR body/description."},
            "base": {"type": "string", "description": "Base branch (optional; defaults to repo default)."},
            "draft": {"type": "boolean", "description": "Create as draft PR (default false)."},
        },
        "required": ["title", "body"],
    },
    requires_approval=True,
    audit_event_type="tool_call_write",
)


# ---------------------------------------------------------------------------
# github_push_branch
# ---------------------------------------------------------------------------

def _push_branch_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    branch: str = inp.get("branch", "").strip()
    force: bool = bool(inp.get("force", False))

    net_err = _network_check(project_root)
    if net_err:
        return NativeToolResult(call_id=call_id, tool_name="github_push_branch", status="blocked", error=net_err)

    if not shutil.which("git"):
        return NativeToolResult(call_id=call_id, tool_name="github_push_branch", status="blocked",
                                error="git not found in PATH.")

    if branch:
        err = _validate_branch(branch)
        if err:
            return NativeToolResult(call_id=call_id, tool_name="github_push_branch", status="error", error=err)

    # Build git push argv — shell=False always.
    git_args = ["git", "push", "-u", "origin"]
    if branch:
        git_args.append(branch)
    else:
        git_args.append("HEAD")
    if force:
        git_args.append("--force")

    try:
        result = subprocess.run(
            git_args,
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT,
            cwd=str(project_root),
        )
    except subprocess.TimeoutExpired:
        return NativeToolResult(call_id=call_id, tool_name="github_push_branch", status="error",
                                error=f"git push timed out after {_GH_TIMEOUT}s")
    except Exception as exc:
        return NativeToolResult(call_id=call_id, tool_name="github_push_branch", status="error",
                                error=f"git push failed: {type(exc).__name__}")

    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    output = redact_secrets(output.strip())

    if result.returncode != 0:
        return NativeToolResult(call_id=call_id, tool_name="github_push_branch", status="error",
                                error=output)

    return NativeToolResult(
        call_id=call_id, tool_name="github_push_branch", status="success",
        output=output,
        metadata={"branch": branch or "HEAD", "force": force, "exit_code": result.returncode},
    )


GITHUB_PUSH_BRANCH_SPEC = NativeToolSpec(
    name="github_push_branch",
    description=(
        "Push the current branch to origin via git push. Approval required. "
        "Set force=true for force push (requires explicit flag). "
        "Requires network: true."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "branch": {"type": "string", "description": "Branch name to push (optional; defaults to HEAD)."},
            "force": {"type": "boolean", "description": "Force push (default false). Use with caution."},
        },
    },
    requires_approval=True,
    audit_event_type="tool_call_write",
)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_github_write_tools(dispatcher: NativeToolDispatcher, project_root: Path) -> None:
    """Register github_create_pr and github_push_branch on a dispatcher."""

    def _pr_handler(call_id: str, inp: dict) -> NativeToolResult:
        return _create_pr_handler(call_id, {"_project_root": str(project_root), **inp})

    def _push_handler(call_id: str, inp: dict) -> NativeToolResult:
        return _push_branch_handler(call_id, {"_project_root": str(project_root), **inp})

    dispatcher.register(GITHUB_CREATE_PR_SPEC, _pr_handler)
    dispatcher.register(GITHUB_PUSH_BRANCH_SPEC, _push_handler)
