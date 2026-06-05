# TypeScript: First Hour with SafeCode Agent

This is the TypeScript-specific companion to [Stack First Hour](stack-first-hour.md).
Use it in a repository with `package.json`. SafeCode defaults to the
deterministic `mock` provider, so no live provider is required. No IDE is required.
All v4.x task/profile/fix-watch/local-delivery surfaces are
EXPERIMENTAL.

## TypeScript Setup Signals

SafeCode detects TypeScript and Node.js projects from `package.json`. `sac
profile detect` reads scripts such as `test`, `lint`, `typecheck`, and `build`
and stores safe command profiles without executing package scripts during
detection.

## First-Hour Flow

```sh
sac quickstart
sac task new "add input validation to the API handler"
sac profile detect
sac status
sac ask "Where is the API request validation logic?"
sac edit "Add Zod validation to the POST /users handler in src/routes/users.ts"
sac apply
sac fix --watch
sac commit --message-from-task
sac debug last-failure
sac rollback --last
```

Useful fix-watch controls:

```sh
sac fix --watch --max-iterations 3
sac fix --watch --rerun-suite test
```

`sac fix --watch` uses the detected test suite from `sac profile detect` when
available. It proposes a pending repair patch on failure and never auto-applies;
review the diff and run `sac apply` explicitly.

## TypeScript Checks

- Make sure `package.json` exposes useful scripts, for example `test`, `lint`,
  or `typecheck`.
- `sac profile detect` may detect npm, pnpm, or yarn commands depending on the
  project.
- Use `sac ask` before `sac edit` when you want a read-only map of routes,
  handlers, or test files.

## Safety Notes

- `sac ask` is read-only.
- `sac edit` creates a pending patch; it does not write project files.
- `sac apply` creates a checkpoint before modifying files.
- `sac rollback --last` restores the latest apply checkpoint.
- No auto-apply, no auto-commit, and no push workflow is implied.

## See Also

- [Stack First Hour](stack-first-hour.md)
- [Python: First Hour](python-first-hour.md)
- [Go: First Hour](go-first-hour.md)
- [MVP User Guide](../mvp-user-guide.md)
