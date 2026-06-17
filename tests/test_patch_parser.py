"""Tests for the SafeCode patch parser."""

import pytest

from safecode.patch.parser import PatchParseError, PatchParser, _strip_to_envelope


def test_parse_update_file_patch() -> None:
    patch_text = """*** Begin Patch
*** Update File: app/main.py
@@
SEARCH:
from fastapi import FastAPI

app = FastAPI()
REPLACE:
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}
*** End Patch"""

    proposal = PatchParser().parse(patch_text, task="add health endpoint")

    assert proposal.task == "add health endpoint"
    assert proposal.status == "pending"
    assert proposal.model == "mock"
    assert len(proposal.blocks) == 1

    block = proposal.blocks[0]
    assert block.operation == "update"
    assert block.file_path.as_posix() == "app/main.py"
    assert block.search == "from fastapi import FastAPI\n\napp = FastAPI()"
    assert '@app.get("/health")' in block.replace


def test_rejects_missing_begin_marker() -> None:
    patch_text = """*** Update File: app/main.py
SEARCH:
old
REPLACE:
new
*** End Patch"""

    with pytest.raises(PatchParseError, match="start"):
        PatchParser().parse(patch_text, task="broken patch")


def test_rejects_empty_search() -> None:
    patch_text = """*** Begin Patch
*** Update File: app/main.py
SEARCH:

REPLACE:
new
*** End Patch"""

    with pytest.raises(PatchParseError, match="SEARCH content cannot be empty"):
        PatchParser().parse(patch_text, task="empty search")


def test_rejects_add_file() -> None:
    patch_text = """*** Begin Patch
*** Add File: app/main.py
SEARCH:
old
REPLACE:
new
*** End Patch"""

    with pytest.raises(PatchParseError, match="Update File only"):
        PatchParser().parse(patch_text, task="add file")


def test_parses_multiple_update_file_blocks() -> None:
    patch_text = """*** Begin Patch
*** Update File: src/users.py
SEARCH:
def load_user(user_id):
REPLACE:
def fetch_user(user_id):
*** Update File: src/views.py
SEARCH:
from users import load_user
REPLACE:
from users import fetch_user
*** Update File: src/audit.py
SEARCH:
from users import load_user
REPLACE:
from users import fetch_user
*** End Patch"""

    proposal = PatchParser().parse(patch_text, task="rename load_user")

    assert len(proposal.blocks) == 3
    paths = [b.file_path.as_posix() for b in proposal.blocks]
    assert paths == ["src/users.py", "src/views.py", "src/audit.py"]
    assert all(b.search.strip() for b in proposal.blocks)
    assert all("fetch_user" in b.replace for b in proposal.blocks)


def test_strips_leading_prose_before_envelope() -> None:
    patch_text = """Phase 1/3: Update the config file.

*** Begin Patch
*** Update File: config.py
SEARCH:
old_value = 1
REPLACE:
old_value = 2
*** End Patch"""

    proposal = PatchParser().parse(patch_text, task="update config")
    assert len(proposal.blocks) == 1
    assert proposal.blocks[0].file_path.as_posix() == "config.py"


def test_strips_trailing_prose_after_envelope() -> None:
    patch_text = """*** Begin Patch
*** Update File: config.py
SEARCH:
old_value = 1
REPLACE:
old_value = 2
*** End Patch

This completes phase 1."""

    proposal = PatchParser().parse(patch_text, task="update config")
    assert len(proposal.blocks) == 1


def test_strip_to_envelope_extracts_correctly() -> None:
    text = "Explanation\n\n*** Begin Patch\n*** Update File: f.py\n*** End Patch\n\nDone."
    result = _strip_to_envelope(text)
    assert result == "*** Begin Patch\n*** Update File: f.py\n*** End Patch"


def test_strip_to_envelope_returns_text_when_no_markers() -> None:
    text = "no markers here"
    result = _strip_to_envelope(text)
    assert result == "no markers here"
