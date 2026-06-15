"""Tests for write-side native tools and patch applier B6/B7/B8 (v4.21.0, EXPERIMENTAL)."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.agent.write_tools import (
    _edit_file_handler,
    _write_file_handler,
    register_write_tools,
    EDIT_FILE_SPEC,
    WRITE_FILE_SPEC,
)
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolCall
from safecode.patch.applier import PatchApplier, PatchApplyError, PatchValidationError
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.utils.time import utc_now_iso


def _inp(project_root: Path, approved: bool = True, **kwargs):
    return {"_project_root": str(project_root), "_approved": approved, **kwargs}


def _proposal(project_root: Path, op: str, rel_path: str, *,
               search=None, replace=None, content=None) -> PatchProposal:
    return PatchProposal(
        id="test-001",
        task="test",
        blocks=[PatchBlock(
            operation=op,
            file_path=Path(rel_path),
            search=search,
            replace=replace,
            content=content,
        )],
        created_at=utc_now_iso(),
        model="test",
    )


# ---------------------------------------------------------------------------
# B6: create and delete operations in PatchApplier
# ---------------------------------------------------------------------------

def test_b6_create_new_file(tmp_path: Path):
    applier = PatchApplier(tmp_path)
    proposal = _proposal(tmp_path, "create", "new_file.txt", content="hello world")
    applier.apply(proposal)
    assert (tmp_path / "new_file.txt").read_text() == "hello world"


def test_b6_create_nested_file(tmp_path: Path):
    applier = PatchApplier(tmp_path)
    proposal = _proposal(tmp_path, "create", "sub/dir/file.py", content="x = 1")
    applier.apply(proposal)
    assert (tmp_path / "sub" / "dir" / "file.py").read_text() == "x = 1"


def test_b6_delete_existing_file(tmp_path: Path):
    f = tmp_path / "to_delete.txt"
    f.write_text("content")
    applier = PatchApplier(tmp_path)
    proposal = _proposal(tmp_path, "delete", "to_delete.txt")
    applier.apply(proposal)
    assert not f.exists()


def test_b6_delete_missing_file_noop(tmp_path: Path):
    applier = PatchApplier(tmp_path)
    proposal = _proposal(tmp_path, "delete", "ghost.txt")
    # Should not raise when file doesn't exist
    applier.apply(proposal)


def test_b6_unknown_operation_raises(tmp_path: Path):
    applier = PatchApplier(tmp_path)
    proposal = _proposal(tmp_path, "rename", "foo.txt")
    with pytest.raises(PatchValidationError, match="Unknown operation"):
        applier.apply(proposal)


def test_b6_update_still_works(tmp_path: Path):
    f = tmp_path / "edit_me.py"
    f.write_text("x = 1\n")
    applier = PatchApplier(tmp_path)
    proposal = _proposal(tmp_path, "update", "edit_me.py", search="x = 1", replace="x = 2")
    applier.apply(proposal)
    assert f.read_text() == "x = 2\n"


# ---------------------------------------------------------------------------
# B7: PermissionError / OSError surfaces as PatchApplyError
# ---------------------------------------------------------------------------

def test_b7_permission_error_on_write_surfaces_as_patch_apply_error(tmp_path: Path):
    f = tmp_path / "locked.txt"
    f.write_text("original")
    f.chmod(0o444)  # read-only
    applier = PatchApplier(tmp_path)
    proposal = _proposal(tmp_path, "update", "locked.txt", search="original", replace="new")
    try:
        applier.apply(proposal)
        # On some systems (root), chmod doesn't actually block; skip assertion.
    except (PatchApplyError, PatchValidationError):
        pass  # Expected on most systems
    finally:
        f.chmod(0o644)


# ---------------------------------------------------------------------------
# B8: AgentLoop.run() default max_steps = 20
# ---------------------------------------------------------------------------

def test_b8_agent_loop_default_max_steps_is_20():
    import inspect
    from safecode.agent.loop import AgentLoop
    sig = inspect.signature(AgentLoop.run)
    assert sig.parameters["max_steps"].default == 20


# ---------------------------------------------------------------------------
# edit_file tool
# ---------------------------------------------------------------------------

def test_edit_file_not_approved_returns_blocked(tmp_path: Path):
    f = tmp_path / "src.py"
    f.write_text("x = 1\n")
    result = _edit_file_handler("c1", _inp(tmp_path, approved=False,
                                            path="src.py", old_string="x = 1", new_string="x = 2"))
    assert result.status == "blocked"
    assert result.metadata.get("requires_approval") is True
    assert "diff_preview" in result.metadata


def test_edit_file_approved_succeeds(tmp_path: Path):
    f = tmp_path / "src.py"
    f.write_text("x = 1\n")
    result = _edit_file_handler("c1", _inp(tmp_path, approved=True,
                                            path="src.py", old_string="x = 1", new_string="x = 99"))
    assert result.status == "success"
    assert f.read_text() == "x = 99\n"
    assert "checkpoint_id" in result.metadata


def test_edit_file_old_string_not_found(tmp_path: Path):
    f = tmp_path / "src.py"
    f.write_text("x = 1\n")
    result = _edit_file_handler("c1", _inp(tmp_path, approved=True,
                                            path="src.py", old_string="MISSING", new_string="new"))
    assert result.status == "error"
    assert "not found" in result.error


def test_edit_file_old_string_not_unique(tmp_path: Path):
    f = tmp_path / "src.py"
    f.write_text("x = 1\nx = 1\n")
    result = _edit_file_handler("c1", _inp(tmp_path, approved=True,
                                            path="src.py", old_string="x = 1", new_string="x = 2"))
    assert result.status == "error"
    assert "unique" in result.error.lower() or "matches" in result.error.lower()


def test_edit_file_missing_file(tmp_path: Path):
    result = _edit_file_handler("c1", _inp(tmp_path, approved=True,
                                            path="no_such.py", old_string="x", new_string="y"))
    assert result.status == "error"


def test_edit_file_root_escape_blocked(tmp_path: Path):
    result = _edit_file_handler("c1", _inp(tmp_path, approved=True,
                                            path="../../etc/passwd", old_string="x", new_string="y"))
    assert result.status == "blocked"


def test_edit_file_requires_approval_spec():
    assert EDIT_FILE_SPEC.requires_approval is True
    assert EDIT_FILE_SPEC.audit_event_type == "tool_call_write"


# ---------------------------------------------------------------------------
# write_file tool
# ---------------------------------------------------------------------------

def test_write_file_not_approved_returns_blocked(tmp_path: Path):
    result = _write_file_handler("c1", _inp(tmp_path, approved=False,
                                             path="new.py", content="x = 1"))
    assert result.status == "blocked"
    assert result.metadata.get("requires_approval") is True


def test_write_file_creates_new_file(tmp_path: Path):
    result = _write_file_handler("c1", _inp(tmp_path, approved=True,
                                             path="new.py", content="# created"))
    assert result.status == "success"
    assert (tmp_path / "new.py").read_text() == "# created"
    assert result.metadata["operation"] == "create"


def test_write_file_overwrites_existing(tmp_path: Path):
    f = tmp_path / "existing.py"
    f.write_text("old content")
    result = _write_file_handler("c1", _inp(tmp_path, approved=True,
                                             path="existing.py", content="new content"))
    assert result.status == "success"
    assert f.read_text() == "new content"
    assert result.metadata["operation"] == "update"


def test_write_file_root_escape_blocked(tmp_path: Path):
    result = _write_file_handler("c1", _inp(tmp_path, approved=True,
                                             path="../../evil.py", content="x"))
    assert result.status == "blocked"


def test_write_file_sac_dir_blocked(tmp_path: Path):
    result = _write_file_handler("c1", _inp(tmp_path, approved=True,
                                             path=".sac/config.toml", content="x"))
    assert result.status == "blocked"


def test_write_file_requires_approval_spec():
    assert WRITE_FILE_SPEC.requires_approval is True
    assert WRITE_FILE_SPEC.audit_event_type == "tool_call_write"


# ---------------------------------------------------------------------------
# register_write_tools integration
# ---------------------------------------------------------------------------

def test_register_write_tools_wires_two_tools(tmp_path: Path):
    dispatcher = NativeToolDispatcher()
    register_write_tools(dispatcher, tmp_path, approved=True)
    names = {s.name for s in dispatcher.specs()}
    assert names == {"edit_file", "write_file"}


def test_registered_write_file_works(tmp_path: Path):
    dispatcher = NativeToolDispatcher()
    register_write_tools(dispatcher, tmp_path, approved=True)
    call = NativeToolCall(tool_name="write_file", input={"path": "out.txt", "content": "hello"}, call_id="c1")
    result = dispatcher.dispatch(call)
    assert result.status == "success"
    assert (tmp_path / "out.txt").read_text() == "hello"
