# Python: First Hour with SafeCode Agent

This is the Python-specific companion to [Stack First Hour](stack-first-hour.md).
Use it in a repository with `pyproject.toml` or `setup.py`. SafeCode defaults
to the deterministic `mock` provider, so no live provider is required. No IDE is required.
All v4.x task/profile/fix-watch/local-delivery surfaces are
EXPERIMENTAL.

## Python Setup Signals

SafeCode detects Python projects from files such as `pyproject.toml`, `setup.py`,
and test layouts. `sac profile detect` looks for commands like `pytest -q`,
`ruff check .`, `mypy`, and build commands without executing unsafe shell
syntax.

## First-Hour Flow

```sh
sac quickstart
sac task new "fix the login validation bug"
sac profile detect
sac status
sac ask "Where is the login validation logic?"
sac edit "Add input length validation to the login function in src/auth.py"
sac apply
sac fix --watch
sac commit --message-from-task
sac debug last-failure
sac rollback --last
```

If you already know the failing test command, you can provide it directly:

```sh
sac fix --test-command "pytest -q"
sac fix --watch --max-iterations 3
```

`sac fix --watch` runs the detected or explicit test command, proposes a pending
repair patch on failure, and never auto-applies. Review the diff, run
`sac apply`, then run `sac fix --watch` again to verify.

## Python Checks

- Use `pytest` for the test suite when available.
- Use `sac profile detect` before `sac fix --watch` so SafeCode can reuse the
  project profile.
- Keep virtualenv and dependency setup outside SafeCode unless you intentionally
  run those commands through `sac run`.

## Safety Notes

- `sac ask` is read-only.
- `sac edit` creates a pending patch; it does not write project files.
- `sac apply` creates a checkpoint before modifying files.
- `sac rollback --last` restores the latest apply checkpoint.
- No auto-apply, no auto-commit, and no push workflow is implied.

## See Also

- [Stack First Hour](stack-first-hour.md)
- [TypeScript: First Hour](typescript-first-hour.md)
- [Go: First Hour](go-first-hour.md)
- [MVP User Guide](../mvp-user-guide.md)
