# Go: First Hour with SafeCode Agent

This tutorial walks you through using SafeCode Agent on a Go project.
Every command shown here is implemented and deterministically testable —
no claims are made about capabilities that do not exist in the codebase.

**Prerequisites**: SafeCode Agent installed (`pip install safecode-agent` or
`pipx install safecode-agent`), Python 3.11+, a Go project with `go.mod`.

---

## 1. Quickstart and stack detection

SafeCode Agent automatically detects Go projects by checking for `go.mod`
in the project root:

```sh
cd my-go-project
sac quickstart
```

When `go.mod` is found, `sac quickstart` adapts next-step hints to Go conventions
(e.g., suggests `go test ./...` as the test command). Unknown or mixed stacks fall
back to the default next-step set.

---

## 2. Ask a read-only question

```sh
sac ask "What does the main package do?"
```

SafeCode Agent collects context (up to `max_context_chars`, default 40,000) and
returns a read-only answer. No files are modified. The LLM provider defaults to
`mock` for local testing — set `provider = "openai"` or `provider = "anthropic"`
in `.sac/config.toml` to use a real model.

---

## 3. Propose an edit

```sh
sac edit "Add error handling to the ReadConfig function in config/config.go"
```

This generates a pending patch proposal and shows a unified diff. **No files
are changed yet.** The pending patch is stored at `.sac/pending_patch.json`.

---

## 4. Review and apply

```sh
sac apply
```

Before applying, you are shown the diff again and asked to confirm. After
confirmation:

- A checkpoint is created (rollback target).
- The patch is applied and validated.
- An audit event is written to the audit log.

---

## 5. Rollback if needed

```sh
sac rollback --last
```

Restores the files modified by the most recent `sac apply` from the checkpoint.
The audit log records the rollback event.

---

## 6. Fix a failing test

If `go test ./...` is your test command:

```sh
sac fix --test-command "go test ./..."
```

SafeCode Agent runs the test command, redacts any secret-like content from the
failure output, and proposes a patch. Review and apply as above.

---

## 7. Check health

```sh
sac doctor
```

Reports installation health, LLM provider config, last session cost (if a live
provider was used), and release metadata.

---

## Stack detection detail

`sac quickstart` detects Go by checking for `go.mod`.
The detection logic is in `src/safecode/cli_quickstart.py`; the detected stack
influences next-step hints but does not change safety behavior.

---

## Safety notes

- All edits go through diff preview, checkpoint, and audit — no file is changed
  silently.
- Network access is disabled by default; enable it explicitly in config to use a
  live LLM provider.
- The `mock` provider is deterministic and requires no network or credentials.
- `go test` is run with `shell=False` (no shell expansion); command args are passed
  as a list to prevent injection.

---

## Related docs

- [SafeCode Agent README](../../README.md)
- [MVP User Guide](../mvp-user-guide.md)
- [Public Contracts](../public-contracts.md)
- [Providers Reference](../providers.md)
- [TypeScript tutorial](typescript-first-hour.md)
