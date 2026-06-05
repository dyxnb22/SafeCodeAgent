"""Deterministic mock-provider agent loop demo for the FastAPI todo example.

This module is EXPERIMENTAL. It records the v4.12 resume-MVP story without
calling a live provider, mutating the source example, pushing, or committing.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


TASK_GOAL = 'add a DELETE /todos/{id} endpoint with a passing test'
EXPECTED_TRANSCRIPT = """# sac demo agent-loop

[setup] provider=mock network=disabled
[setup] source=examples/fastapi-todo
[setup] working-copy=<temp-worktree>

[task] add a DELETE /todos/{id} endpoint with a passing test

[plan]
1. Inspect the FastAPI routes and in-memory store.
2. Add a store delete helper and DELETE /todos/{id} endpoint.
3. Add a baseline test for deleting an existing todo and a missing todo.
4. Run pytest through the project test command.

[patch proposal]
M src/todo_api/store.py
M src/todo_api/app.py
M tests/test_app.py

[review boundary]
Review the diff before apply. The demo pauses here in a real agent run.

[approve]
User approval is required before apply. This mock transcript records approval without changing the source example.

[apply boundary]
Patch is applied only inside <temp-worktree>.

[validation]
$ PYTHONPATH=src pytest -q
5 passed

[commit prompt]
Suggested local commit: feat(todo-api): add delete todo endpoint
No commit was created by this demo. No push or pull request was attempted.

[cleanup]
Removed <temp-worktree>
"""


@dataclass(frozen=True)
class AgentLoopDemoResult:
    """Result of one deterministic demo run."""

    transcript: str
    source_root: Path
    temp_parent: Path
    working_copy: Path
    cleanup_done: bool


def run_agent_loop_demo(project_root: Path | None = None) -> AgentLoopDemoResult:
    """Run the deterministic mock-provider transcript in a temp working copy."""
    root = (project_root or Path.cwd()).resolve()
    source_root = root / "examples" / "fastapi-todo"
    if not source_root.is_dir():
        raise FileNotFoundError(f"FastAPI todo example not found: {source_root}")

    temp_parent = Path(tempfile.mkdtemp(prefix="sac-agent-loop-demo-"))
    working_copy = temp_parent / "fastapi-todo"
    cleanup_done = False
    try:
        ignore = shutil.ignore_patterns(".pytest_cache", "__pycache__", "*.pyc")
        shutil.copytree(source_root, working_copy, ignore=ignore)
        _apply_mock_delete_endpoint_patch(working_copy)
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)
        cleanup_done = not temp_parent.exists()

    return AgentLoopDemoResult(
        transcript=EXPECTED_TRANSCRIPT,
        source_root=source_root,
        temp_parent=temp_parent,
        working_copy=working_copy,
        cleanup_done=cleanup_done,
    )


def _apply_mock_delete_endpoint_patch(working_copy: Path) -> None:
    """Apply the deterministic future patch inside the copied example only."""
    store_path = working_copy / "src" / "todo_api" / "store.py"
    app_path = working_copy / "src" / "todo_api" / "app.py"
    test_path = working_copy / "tests" / "test_app.py"

    store_text = store_path.read_text(encoding="utf-8")
    store_text = store_text.replace(
        "    def create(self, title: str, completed: bool = False) -> dict[str, int | str | bool]:\n"
        "        todo = Todo(id=self._next_id, title=title, completed=completed)\n"
        "        self._items[todo.id] = todo\n"
        "        self._next_id += 1\n"
        "        return todo.as_dict()\n",
        "    def create(self, title: str, completed: bool = False) -> dict[str, int | str | bool]:\n"
        "        todo = Todo(id=self._next_id, title=title, completed=completed)\n"
        "        self._items[todo.id] = todo\n"
        "        self._next_id += 1\n"
        "        return todo.as_dict()\n\n"
        "    def delete(self, todo_id: int) -> bool:\n"
        "        return self._items.pop(todo_id, None) is not None\n",
    )
    store_path.write_text(store_text, encoding="utf-8")

    app_text = app_path.read_text(encoding="utf-8")
    app_text = app_text.replace("from fastapi import FastAPI\n", "from fastapi import FastAPI, HTTPException\n")
    app_text += (
        "\n\n@app.delete(\"/todos/{todo_id}\", status_code=204)\n"
        "def delete_todo(todo_id: int) -> None:\n"
        "    \"\"\"Delete one todo by id.\"\"\"\n"
        "    if not store.delete(todo_id):\n"
        "        raise HTTPException(status_code=404, detail=\"Todo not found\")\n"
    )
    app_path.write_text(app_text, encoding="utf-8")

    test_text = test_path.read_text(encoding="utf-8")
    test_text += (
        "\n\n"
        "def test_delete_todo_removes_existing_item():\n"
        "    api = client()\n"
        "    created = api.post(\"/todos\", json={\"title\": \"delete me\"}).json()\n\n"
        "    response = api.delete(f\"/todos/{created['id']}\")\n\n"
        "    assert response.status_code == 204\n"
        "    assert api.get(\"/todos\").json() == []\n"
    )
    test_path.write_text(test_text, encoding="utf-8")
