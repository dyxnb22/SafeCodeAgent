# Go: First Hour with SafeCode Agent

This tutorial walks you through using SafeCode Agent on a Go project
following the v4.x task-first daily loop. Every command shown here exists
in the codebase and is deterministically testable.

**Prerequisites**: SafeCode Agent installed, Python 3.11+, a Go project with
`go.mod`.

No live LLM provider is required to follow these steps — the default provider
is `mock`. No IDE is required. No auto-apply, no auto-commit, no push.

---

## 1. Start: quickstart and stack detection

```sh
cd my-go-project
sac quickstart
```

`sac quickstart` checks your `.sac/config.toml`, shows the current
provider/policy, detects the Go stack (when `go.mod` is present), and prints
next-step commands tailored to Go conventions. No files are modified.

---

## 2. Create a task

```sh
sac task new "fix the HTTP handler error handling"
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

`sac profile detect` scans the project for Go test/vet/build commands without
executing them. The detected profile is stored at `.sac/project_profile.json`
and used by `sac fix --watch` to know which test suite to run.

```sh
sac profile show
```

Shows the detected commands. Use `sac profile set test "go test ./..."` to
override if detection missed something.

---

## 4. Check status

```sh
sac status
```

`sac status` shows the current task id/goal/status, whether a pending patch is
waiting for review, the last test outcome, the last command, and the next safe
step. Run it any time you want to know what to do next.

---

## 5. Ask a read-only question

```sh
sac ask "How does the HTTP router handle 404 errors?"
```

`sac ask` collects project context and returns a read-only answer. No files are
modified. The LLM provider defaults to `mock` for local testing — configure
`provider = "openai"` or `provider = "anthropic"` in `.sac/config.toml` for
real answers.

---

## 6. Propose an edit

```sh
sac edit "Return a structured error response in the handler in internal/api/handler.go"
```

`sac edit` generates a pending patch proposal and shows a unified diff.
**No files are changed yet.** The pending patch is stored at
`.sac/pending_patch.json`. Review the diff before proceeding.

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
and if tests fail, proposes a patch to repair them. **It never auto-applies.**
After review, run `sac apply` and then re-run `sac fix --watch` to verify.

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
This is always available as a recovery path.

---

## 10. Commit the task locally

```sh
sac commit
```

`sac commit` stages only the files derived from the current task's applied
checkpoint, writes a commit message from the task goal, and commits locally.
**No push, no remote operations.**

---

## 11. Resume after interruption

If you press Ctrl-C during `sac edit` or `sac fix`, the current task is marked
`interrupted`. Resume later with:

```sh
sac resume
```

---

## 12. Inspect failures

```sh
sac debug last-failure
```

Shows a redacted summary of the last failure. Read-only.

```sh
sac debug bundle
```

Creates a redacted tar.gz diagnostic bundle (bounded to 5 MiB). Project source
code is excluded.

---

## Safety notes

- `sac edit` never writes to project files — it creates a pending patch only.
- `sac apply` always creates a checkpoint first; `sac rollback --last` restores it.
- `sac fix --watch` never auto-applies; each iteration requires explicit `sac apply`.
- `sac commit` never pushes; no remote operations occur.
- Network access defaults to disabled.
- All v4.x commands (`sac task`, `sac profile`, `sac fix --watch`, `sac commit`,
  `sac resume`, `sac debug`) are EXPERIMENTAL. They may change in future releases.

---

## See also

- [MVP User Guide](../mvp-user-guide.md)
- [Troubleshooting](../troubleshooting.md)
- [Public Contracts](../public-contracts.md)
- [Python Tutorial](python-first-hour.md)
- [TypeScript Tutorial](typescript-first-hour.md)
