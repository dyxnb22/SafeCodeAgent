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

| Stack | Detection Signals | Useful Commands |
| --- | --- | --- |
| Python | `pyproject.toml`, `setup.py`, test layouts | `pytest -q`, `ruff check .`, `mypy` |
| TypeScript | `package.json` | `npm test`, `npm run lint`, `npm run typecheck`, `npm run build` |
| Go | `go.mod` | `go test ./...`, `go vet ./...`, `go build ./...` |

If you already know the failing test command, pass it directly:

```sh
sac fix --test-command "pytest -q"
sac fix --test-command "go test ./..."
sac fix --watch --max-iterations 3
```

For TypeScript projects, make sure `package.json` exposes scripts such as
`test`, `lint`, or `typecheck`. For Go projects, keep `go.mod` at the project
root so stack detection can find it. Use `sac ask` before `sac edit` when you
want a read-only map of routes, handlers, packages, or tests.

## Safety Notes

- No auto-apply and no auto-commit.
- `sac rollback --last` restores the latest apply checkpoint.
- `sac commit` is local only and task-aware.
- High-risk shell commands remain policy-gated.
- Live providers require explicit user and project configuration.

## See Also

- [User Guide](../user-guide.md)
- [Command Reference](../reference/commands.md)
