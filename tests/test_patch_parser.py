"""Tests for the SafeCode patch parser."""

import pytest

from safecode.patch.parser import PatchParseError, PatchParser


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


def test_rejects_add_file_for_v0_1_1() -> None:
    patch_text = """*** Begin Patch
*** Add File: app/main.py
SEARCH:
old
REPLACE:
new
*** End Patch"""

    with pytest.raises(PatchParseError, match="Update File only"):
        PatchParser().parse(patch_text, task="add file")


def test_rejects_multiple_operations() -> None:
    patch_text = """*** Begin Patch
*** Update File: app/main.py
SEARCH:
old
REPLACE:
new
*** Update File: app/other.py
SEARCH:
old
REPLACE:
new
*** End Patch"""

    with pytest.raises(PatchParseError, match="only one file operation"):
        PatchParser().parse(patch_text, task="multiple files")
