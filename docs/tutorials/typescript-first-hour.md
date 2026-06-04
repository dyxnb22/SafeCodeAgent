# TypeScript: First Hour with SafeCode Agent

This tutorial walks you through using SafeCode Agent on a TypeScript project.
Every command shown here is implemented and deterministically testable —
no claims are made about capabilities that do not exist in the codebase.

**Prerequisites**: SafeCode Agent installed (`pip install safecode-agent` or
`pipx install safecode-agent`), Python 3.11+, a TypeScript project with
`package.json`.

---

## 1. Quickstart and stack detection

SafeCode Agent automatically detects TypeScript projects by checking for
`package.json` in the project root:

```sh
cd my-typescript-project
sac quickstart
```

When `package.json` is found, `sac quickstart` adapts next-step commands to
TypeScript conventions (e.g., suggests `npm test` or `npx tsc` as test/build
commands). Unknown or mixed stacks fall back to the default next-step set.

---

## 2. Ask a read-only question

```sh
sac ask "What does the main entry point do?"
```

SafeCode Agent collects context (up to `max_context_chars`, default 40,000) and
returns a read-only answer. No files are modified. The LLM provider defaults to
`mock` for local testing — set `provider = "openai"` in `.sac/config.toml` to
use a real model.

---

## 3. Propose an edit

```sh
sac edit "Add a type annotation to the greet function in src/greet.ts"
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

If `npm test` or `npx jest` is your test command:

```sh
sac fix --test-command "npm test"
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

`sac quickstart` detects TypeScript by checking for `package.json`.
The detection logic is in `src/safecode/cli_quickstart.py`; the detected stack
influences next-step hints but does not change safety behavior.

---

## Safety notes

- All edits go through diff preview, checkpoint, and audit — no file is changed
  silently.
- Network access is disabled by default; enable it explicitly in config to use a
  live LLM provider.
- The `mock` provider is deterministic and requires no network or credentials.

---

## Related docs

- [SafeCode Agent README](../../README.md)
- [MVP User Guide](../mvp-user-guide.md)
- [Public Contracts](../public-contracts.md)
- [Providers Reference](../providers.md)
- [Go tutorial](go-first-hour.md)
