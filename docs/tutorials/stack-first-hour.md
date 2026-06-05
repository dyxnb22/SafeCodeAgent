# Stack First Hour with SafeCode Agent

Use this shared flow for Python, TypeScript, Go, and similar local projects.
The stack-specific tutorials only add language details.

SafeCode defaults to the deterministic `mock` provider, so no live provider is
required. No IDE is required. All v4.x task/profile/fix-watch/local-delivery
surfaces below are EXPERIMENTAL.

## Shared Flow

```sh
sac quickstart
sac task new "make one small safe change"
sac profile detect
sac status
sac ask "Where should this change be made?"
sac edit "Make the smallest safe change"
sac apply
sac fix --watch
sac commit --message-from-task
sac debug last-failure
sac rollback --last
```

`sac quickstart` detects the stack and prints next steps. `sac profile detect`
records test/lint/typecheck/build commands when they can be detected. `sac ask`
is read-only. `sac edit` creates a pending patch and diff. `sac apply` is the
explicit checkpoint-and-apply step. `sac fix --watch` runs one bounded test-fix
iteration and never auto-applies; review the diff and run `sac apply` yourself.

## Stack Hints

- Python: expect `pyproject.toml`, `setup.py`, `pytest`, `ruff`, or `mypy`.
- TypeScript: expect `package.json` scripts such as `test`, `lint`, or `typecheck`.
- Go: expect `go.mod`, `go test ./...`, `go vet`, and `go build`.

## Safety Notes

- No auto-apply and no auto-commit.
- `sac rollback --last` restores the latest apply checkpoint.
- `sac commit` is local only and task-aware.
- High-risk shell commands remain policy-gated.
- Live providers require explicit user and project configuration.

## See Also

- [Python: First Hour](python-first-hour.md)
- [TypeScript: First Hour](typescript-first-hour.md)
- [Go: First Hour](go-first-hour.md)
