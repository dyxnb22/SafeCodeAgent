# FastAPI Todo Example

This is a small, realistic FastAPI project used as the SafeCode Agent demo target. It is intentionally outside the SafeCode package import path and keeps state in memory so local edits are easy to review.

A reference command profile lives at `fixtures/project_profile.json` (not under `.sac/`). Run `sac profile detect` in this directory to materialize `.sac/project_profile.json` locally when needed.

Run the baseline:

```sh
uv sync --extra examples
cd examples/fastapi-todo
pytest -q
```

Try the intended agent task from the example directory:

```sh
sac agent run "add a DELETE /todos/{id} endpoint with a passing test"
```

Safety note: review the proposed diff before apply. The demo does not auto-apply, auto-commit, push, or create a pull request.
