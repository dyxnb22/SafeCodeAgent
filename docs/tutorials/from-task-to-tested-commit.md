# From Task to Tested Commit

The v4.12 demo is an EXPERIMENTAL, mock-only walkthrough of the SafeCode agent loop. It uses `examples/fastapi-todo/`, records every mutation boundary, and does not require a live provider, IDE, push, pull request, auto-apply, or auto-commit.

## Run the Baseline

```sh
uv sync --extra examples
cd examples/fastapi-todo
pytest -q
```

The example starts with `GET /todos`, `POST /todos`, an in-memory store, and four tests. The natural task is:

```sh
sac agent run "add a DELETE /todos/{id} endpoint with a passing test"
```

## Reproduce the Transcript

From the repository root:

```sh
examples/fastapi-todo/demo/run-demo.sh
sac demo agent-loop
```

The recorded output lives at `examples/fastapi-todo/demo/expected-transcript.md`. It uses stable placeholders such as `<temp-worktree>` instead of timestamps or ids.

## What the Transcript Shows

The demo follows the same safety shape as the real EXPERIMENTAL agent loop:

1. A task goal is captured.
2. A plan is shown before edits.
3. A patch proposal lists the files that would change.
4. The review boundary requires a human to inspect the diff.
5. The apply boundary requires approval before mutation.
6. Validation runs with `PYTHONPATH=src pytest -q`.
7. A local commit message is suggested, but no commit is created by the demo.

The script copies `examples/fastapi-todo/` to a temporary working directory before it does anything. The source example in the repository is not mutated.
