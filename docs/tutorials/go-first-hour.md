# Go: First Hour with SafeCode Agent

This is the Go-specific companion to [Stack First Hour](stack-first-hour.md).
Use it in a repository with `go.mod`. SafeCode defaults to the deterministic
`mock` provider, so no live provider is required. No IDE is required. All v4.x
task/profile/fix-watch/local-delivery surfaces are EXPERIMENTAL.

## Go Setup Signals

SafeCode detects Go projects from `go.mod`. `sac profile detect` looks for
commands such as `go test ./...`, `go vet ./...`, and `go build ./...` and
stores them in the project profile.

## First-Hour Flow

```sh
sac quickstart
sac task new "fix the HTTP handler error handling"
sac profile detect
sac status
sac ask "How does the HTTP router handle 404 errors?"
sac edit "Return a structured error response in internal/api/handler.go"
sac apply
sac fix --watch
sac commit --message-from-task
sac debug last-failure
sac rollback --last
```

Useful fix-watch controls:

```sh
sac fix --test-command "go test ./..."
sac fix --watch --max-iterations 3
```

`sac fix --watch` uses the detected Go test command when available. It proposes
a pending repair patch on failure and never auto-applies; review the diff and
run `sac apply` explicitly.

## Go Checks

- Keep `go.mod` at the project root for stack detection.
- Use `sac profile detect` so SafeCode can reuse `go test`, `go vet`, and
  `go build` commands.
- Use `sac ask` before `sac edit` when you want a read-only map of packages,
  handlers, or tests.

## Safety Notes

- `sac ask` is read-only.
- `sac edit` creates a pending patch; it does not write project files.
- `sac apply` creates a checkpoint before modifying files.
- `sac rollback --last` restores the latest apply checkpoint.
- No auto-apply, no auto-commit, and no push workflow is implied.

## See Also

- [Stack First Hour](stack-first-hour.md)
- [Python: First Hour](python-first-hour.md)
- [TypeScript: First Hour](typescript-first-hour.md)
- [MVP User Guide](../mvp-user-guide.md)
