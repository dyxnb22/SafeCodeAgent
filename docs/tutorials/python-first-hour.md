# Python: First Hour with SafeCode Agent

This tutorial walks you through using SafeCode Agent on a Python project
following the v4.x task-first daily loop. Every command shown here exists
in the codebase and is deterministically testable.

**Prerequisites**: SafeCode Agent installed, Python 3.11+, a Python project
with `pyproject.toml` or `setup.py`.

No live LLM provider is required to follow these steps — the default provider
is `mock`. No IDE is required. No auto-apply, no auto-commit, no push.

---

## 1. Start: quickstart and stack detection

```sh
cd my-python-project
sac quickstart
```

`sac quickstart` checks your `.sac/config.toml`, shows the current
provider/policy, detects the project stack (Python when `pyproject.toml` is
present), and prints next-step commands tailored to the stack. No files are
modified.

---

## 2. Create a task

```sh
sac task new "fix the login validation bug"
```

`sac task new <goal>` creates a task sidecar under `.sac/tasks/` and sets it
as `CURRENT`. All subsequent `sac edit`, `sac apply`, `sac fix`, and `sac run`
invocations attach to this task automatically. The task starts with status
`open`.

---

## 3. Detect project profile

```sh
sac profile detect
```

`sac profile detect` scans the project for Python test/lint/typecheck/build
commands (pytest, ruff, mypy, etc.) without executing them. The detected
profile is stored at `.sac/project_profile.json` and used by `sac fix
--watch` to know which test suite to run.

```sh
sac profile show
```

Shows the detected commands. Use `sac profile set test "pytest -q"` to
override a specific kind if the detection missed something.

---

## 4. Check status

```sh
sac status
```

`sac status` shows the current task id/goal/status, whether a pending patch is
waiting for review, the last test outcome, the last command, and the next safe
step. This is the primary orientation command — run it any time you want to
know what to do next.

---

## 5. Ask a read-only question

```sh
sac ask "Where is the login validation logic?"
```

`sac ask` collects project context and returns a read-only answer. No files are
modified. The LLM provider defaults to `mock` for local testing — configure
`provider = "openai"` or `provider = "anthropic"` in `.sac/config.toml` for
real answers.

---

## 6. Propose an edit

```sh
sac edit "Add input length validation to the login function in src/auth.py"
```

`sac edit` generates a pending patch proposal and shows a unified diff.
**No files are changed yet.** The pending patch is stored at
`.sac/pending_patch.json`. Review the diff before proceeding.

Review what was proposed:

```sh
sac status
```

---

## 7. Apply the patch

```sh
sac apply
```

`sac apply` validates the patch, creates a checkpoint (backup of the files to
be changed), writes the patch to disk, and emits an audit event. The original
files are preserved in the checkpoint directory so you can roll back.

---

## 8. Fix a failing test with the watch loop

If a test is failing, use the fix loop instead of a manual edit:

```sh
sac fix --watch
```

`sac fix --watch` runs the detected test suite (from `sac profile detect`),
and if tests fail, proposes a patch to repair them. The loop then waits for
you to run `sac apply`. **It never auto-applies.** After applying, re-run
`sac fix --watch` to verify the repair.

Limit iterations explicitly:

```sh
sac fix --watch --max-iterations 3
```

---

## 9. Roll back if needed

```sh
sac rollback --last
```

`sac rollback --last` restores the files modified by the latest checkpoint.
This is always available as a recovery path. If the checkpoint files appear
committed to git, rollback will warn you and suggest `git revert` instead;
use `--force-uncommit` explicitly if you understand the risk.

---

## 10. Commit the task locally

```sh
sac commit
```

`sac commit` stages only the files derived from the current task's applied
checkpoint, writes a deterministic commit message from the task goal, and
commits locally. **No push, no remote operations.** If unrelated tracked
changes are staged, the commit is refused — use `--allow-unrelated-changes`
explicitly if needed.

---

## 11. Resume after interruption

If you press Ctrl-C during `sac edit`, `sac fix`, or `sac run`, the current
task is marked `interrupted`. Resume later with:

```sh
sac resume
```

`sac resume` finds the interrupted task, sets it as `CURRENT`, and prints the
next safe step without running anything automatically.

---

## 12. Inspect failures and create a debug bundle

If something went wrong:

```sh
sac debug last-failure
```

Shows a redacted summary of the last failure (category, message, suggested
next command) from runtime logs, task sidecars, and audit events. Read-only.

To collect a full diagnostic bundle:

```sh
sac debug bundle
```

Creates a redacted tar.gz under `.sac/debug/` with version metadata, config
snapshot, runtime logs, verified audit events, task sidecars, and memory
metadata. Project source code is excluded. The bundle is bounded to 5 MiB.

---

## Safety notes

- `sac edit` never writes to project files — it creates a pending patch only.
- `sac apply` always creates a checkpoint first; `sac rollback --last` restores it.
- `sac fix --watch` never auto-applies; each iteration requires explicit `sac apply`.
- `sac commit` never pushes; no remote operations occur.
- Network access defaults to disabled. Set `network = true` in `.sac/config.toml`
  only when using a live LLM provider.
- All v4.x commands (`sac task`, `sac profile`, `sac fix --watch`, `sac commit`,
  `sac resume`, `sac debug`) are EXPERIMENTAL. They may change in future releases.

---

## See also

- [MVP User Guide](../mvp-user-guide.md)
- [Troubleshooting](../troubleshooting.md)
- [Public Contracts](../public-contracts.md)
- [TypeScript Tutorial](typescript-first-hour.md)
- [Go Tutorial](go-first-hour.md)
