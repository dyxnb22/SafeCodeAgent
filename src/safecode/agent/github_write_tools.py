"""GitHub write native tools via `gh` CLI and `git` (v6.4.0 — stable contract).

Tools: github_create_pr, github_push_branch

Stable invariants (Section 20 of public-contracts.md):
- github_push_branch ALWAYS rejects pushes to protected branches (main, master,
  trunk). This is a structural code-level gate, not just a documentation note.
- PR body is always enriched with a SafeCode audit footer (branch, checkpoint
  reference, timestamp). Users see this in the approval preview before execution.
- dry_run=True validates all inputs and builds the preview but does not call
  the network. Safe to use in scripting and tests.
- requires_approval=True is stable: no push or PR creation occurs without a
  human approval step.
- Failure never corrupts local checkpoint or pending patch state: all local
  state mutations (checkpoint, pending patch) precede the network call.
- audit_event_type="github_pr_created" for create_pr is stable.
- audit_event_type="github_branch_pushed" for push_branch is stable.
- All subprocess calls use shell=False argv lists (no shell injection).
- branch names validated against _SAFE_BRANCH pattern.
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

from safecode.agent.github_read_tools import _gh_available, _network_check, _run_gh
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolResult, NativeToolSpec
from safecode.context.redactor import redact_secrets

_SAFE_BRANCH = re.compile(r"^[a-zA-Z0-9._/-]{1,200}$")
_GH_TIMEOUT = 30

# Structural block: these branches can never be pushed to via github_push_branch.
# This is a code-level invariant, not a configuration option.
PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "master", "trunk"})


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _validate_branch(name: str) -> str | None:
    if not name or not _SAFE_BRANCH.match(name):
        return f"Invalid branch name: {name!r}"
    if name.startswith("-"):
        return f"Branch name must not start with '-': {name!r}"
    return None


def _get_current_branch(project_root: Path) -> str | None:
    """Return the name of the current git branch, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True,
            cwd=str(project_root), shell=False, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _latest_checkpoint_id(project_root: Path) -> str:
    """Return the most recent checkpoint ID, or 'none' if no checkpoints exist."""
    try:
        from safecode.checkpoint.manager import CheckpointManager
        manager = CheckpointManager(project_root)
        checkpoints = manager.list_checkpoints()
        if checkpoints:
            return checkpoints[-1].checkpoint_id
    except Exception:
        pass
    return "none"


def _build_pr_footer(project_root: Path, branch: str) -> str:
    """Build the stable SafeCode audit footer appended to every PR body."""
    from safecode.utils.time import utc_now_iso
    checkpoint_id = _latest_checkpoint_id(project_root)
    return (
        "\n\n---\n"
        "**SafeCode Audit Reference**\n"
        f"- Branch: `{branch}`\n"
        f"- Checkpoint: `{checkpoint_id}`\n"
        f"- Created: {utc_now_iso()}\n"
        f"- Tool: SafeCode Agent `github_create_pr`\n"
    )


def _blocked(call_id: str, tool: str, msg: str) -> NativeToolResult:
    return NativeToolResult(call_id=call_id, tool_name=tool, status="blocked", error=msg)


def _error(call_id: str, tool: str, msg: str) -> NativeToolResult:
    return NativeToolResult(call_id=call_id, tool_name=tool, status="error", error=msg)


# ---------------------------------------------------------------------------
# github_create_pr
# ---------------------------------------------------------------------------

def _create_pr_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    title: str = inp.get("title", "").strip()
    body: str = inp.get("body", "").strip()
    base: str = inp.get("base", "").strip()
    draft: bool = bool(inp.get("draft", False))
    dry_run: bool = bool(inp.get("dry_run", False))

    net_err = _network_check(project_root)
    if net_err:
        return _blocked(call_id, "github_create_pr", net_err)

    if not _gh_available():
        return _blocked(call_id, "github_create_pr", "gh CLI not found; install GitHub CLI.")

    if not title:
        return _error(call_id, "github_create_pr", "Missing 'title' input.")

    if base:
        err = _validate_branch(base)
        if err:
            return _error(call_id, "github_create_pr", err)

    # Detect current branch for footer.
    current_branch = _get_current_branch(project_root) or "unknown"

    # Build enriched body — footer always appended (stable contract invariant).
    footer = _build_pr_footer(project_root, current_branch)
    enriched_body = body + footer

    if dry_run:
        preview = f"[DRY RUN] Would create PR:\nTitle: {title}\nBase: {base or '(default)'}\nDraft: {draft}\n{enriched_body}"
        return NativeToolResult(
            call_id=call_id, tool_name="github_create_pr", status="success",
            output=preview,
            metadata={"dry_run": True, "title": title, "base": base, "draft": draft},
        )

    args = ["pr", "create", "--title", title, "--body", enriched_body]
    if base:
        args += ["--base", base]
    if draft:
        args.append("--draft")

    ok, output = _run_gh(args)
    if not ok:
        return _error(call_id, "github_create_pr", redact_secrets(output))

    pr_url = output.strip()
    return NativeToolResult(
        call_id=call_id, tool_name="github_create_pr", status="success",
        output=redact_secrets(pr_url),
        metadata={"pr_url": pr_url, "draft": draft, "branch": current_branch},
    )


GITHUB_CREATE_PR_SPEC = NativeToolSpec(
    name="github_create_pr",
    description=(
        "Create a GitHub pull request via gh CLI. Approval required. "
        "PR body is automatically enriched with a SafeCode audit footer. "
        "Set dry_run=true to preview without creating. "
        "Requires network: true."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "PR title."},
            "body": {"type": "string", "description": "PR body/description."},
            "base": {"type": "string", "description": "Base branch (optional; defaults to repo default)."},
            "draft": {"type": "boolean", "description": "Create as draft PR (default false)."},
            "dry_run": {"type": "boolean", "description": "Preview PR without creating it (default false)."},
        },
        "required": ["title", "body"],
    },
    requires_approval=True,
    audit_event_type="github_pr_created",  # stable event type (Section 20)
)


# ---------------------------------------------------------------------------
# github_push_branch
# ---------------------------------------------------------------------------

def _push_branch_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    branch: str = inp.get("branch", "").strip()
    force: bool = bool(inp.get("force", False))
    dry_run: bool = bool(inp.get("dry_run", False))

    net_err = _network_check(project_root)
    if net_err:
        return _blocked(call_id, "github_push_branch", net_err)

    if not shutil.which("git"):
        return _blocked(call_id, "github_push_branch", "git not found in PATH.")

    if branch:
        err = _validate_branch(branch)
        if err:
            return _error(call_id, "github_push_branch", err)

    # Resolve which branch will actually be pushed.
    target_branch = branch or _get_current_branch(project_root) or ""

    # STRUCTURAL GATE: never push to protected branches (code-level, not config).
    if target_branch.lower() in PROTECTED_BRANCHES:
        return _blocked(
            call_id, "github_push_branch",
            f"Pushing to '{target_branch}' is not allowed. "
            "Create a feature branch and push that instead. "
            "This block cannot be overridden by configuration.",
        )

    if dry_run:
        preview = (
            f"[DRY RUN] Would push branch: {target_branch or 'HEAD'} "
            f"(force={force}) to origin."
        )
        return NativeToolResult(
            call_id=call_id, tool_name="github_push_branch", status="success",
            output=preview,
            metadata={"dry_run": True, "branch": target_branch, "force": force},
        )

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
            capture_output=True, text=True,
            timeout=_GH_TIMEOUT,
            cwd=str(project_root),
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return _error(call_id, "github_push_branch", f"git push timed out after {_GH_TIMEOUT}s")
    except Exception as exc:
        return _error(call_id, "github_push_branch", f"git push failed: {type(exc).__name__}")

    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    output = redact_secrets(output.strip())

    if result.returncode != 0:
        return _error(call_id, "github_push_branch", output)

    return NativeToolResult(
        call_id=call_id, tool_name="github_push_branch", status="success",
        output=output,
        metadata={"branch": target_branch or "HEAD", "force": force, "exit_code": result.returncode},
    )


GITHUB_PUSH_BRANCH_SPEC = NativeToolSpec(
    name="github_push_branch",
    description=(
        "Push the current branch to origin via git push. Approval required. "
        "Pushes to main, master, and trunk are always blocked. "
        "Set force=true for force push (requires explicit flag). "
        "Set dry_run=true to preview without pushing. "
        "Requires network: true."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "branch": {"type": "string", "description": "Branch name to push (optional; defaults to HEAD)."},
            "force": {"type": "boolean", "description": "Force push (default false). Use with caution."},
            "dry_run": {"type": "boolean", "description": "Preview push without executing it (default false)."},
        },
    },
    requires_approval=True,
    audit_event_type="github_branch_pushed",  # stable event type (Section 20)
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
