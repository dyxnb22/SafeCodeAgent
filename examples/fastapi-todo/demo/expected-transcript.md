# sac demo agent-loop

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
