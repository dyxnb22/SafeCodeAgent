# SafeCode Realistic Demo Transcript

Scenario: a todo service has an API facade and in-memory store. Two tests fail:

1. New todos should be open by default.
2. Completed todos should not appear in `list_open_todos()`.

## User Goal

```text
Fix the todo service so new todos start as open and list_open_todos excludes
completed items. Run pytest to verify.
```

## Context

SafeCode reads:

- `src/todo_service/api.py`
- `src/todo_service/store.py`
- `tests/test_todo_service.py`

The failing assertions point to store behavior, not the API facade.

## Diff Preview

```diff
--- a/src/todo_service/store.py
+++ b/src/todo_service/store.py
@@
-        item = Todo(id=self._next_id, title=title, completed=True)
+        item = Todo(id=self._next_id, title=title, completed=False)
@@
-        return list(self._items)
+        return [item for item in self._items if not item.completed]
```

## Safety Gates

```text
[review boundary] user approves the diff
[checkpoint] sha256 backup created for src/todo_service/store.py
[apply] patch applied
[audit] hash-chain event appended
```

## Verification

```text
python3 -m pytest tests/test_todo_service.py -q
..                                                                       [100%]
2 passed
```

## Rollback

Rollback remains available:

```bash
sac rollback --last
```

## Why This Demo Matters

Unlike the tiny calculator demo, this one includes a facade, store, and tests.
The fix is still small, but the agent must identify that the right change is
inside the store layer and verify the API-facing behavior through tests.
