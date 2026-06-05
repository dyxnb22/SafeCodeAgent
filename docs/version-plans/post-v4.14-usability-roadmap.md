# Post-v4.14 Usability Roadmap

Status: COMPLETED as of `v4.16.2`.
Baseline: `v4.14.0` provider-profile UX release.
Last updated: 2026-06-05.
Completed: 2026-06-05 (v4.14.1 through v4.16.2 all shipped and tagged).
Next active plan: `docs/version-plans/post-v4.16-shell-ux-roadmap.md`.

## Goal

Make SafeCode Agent feel obvious in the first five minutes while preserving its
safety-first contract: explicit apply and commit boundaries, no surprise
network access, no project-local credentials, and clear user/project config
separation.

The product direction is closer to Claude Code and Reasonix in day-to-day
ergonomics: a discoverable interactive entry, clear model switching, provider
setup by account/profile, and errors that say exactly what to run next.

## Non-Goals

- No auto-apply, auto-commit, push, PR, background task, RAG, embeddings,
  LangGraph, or cloud execution.
- No stable-contract promotion.
- No project-local credential storage.
- No hidden weakening of user-level network or safety policy.
- No removal of existing advanced commands; command-surface trimming must keep
  hidden commands callable for compatibility.

## Top Usability Problems

1. Bare `sac` does not provide a useful first-run path in TTY mode.
2. `sac setup`, `sac setup --wizard`, `sac quickstart`, and
   `sac provider add` overlap as entry points.
3. `sac model <alias>` persists globally, while users expect session-scoped
   switching by default.
4. Credential UX is split across env vars, user TOML, and diagnostics, with no
   keychain or env-only flow.
5. The visible top-level command surface has grown back to roughly 20 commands.
6. `sac shell` has the right interaction model but is not the default entry.
7. Doctor/provider failures often lack a concrete next command on the failing
   row.
8. Legacy `[llm]` and `[providers.<name>]` coexist without a visible precedence
   trace or migration command.
9. `sac provider status` and `sac doctor` lack a top-line READY/BROKEN verdict.
10. Root `sac --model ...` is useful but not discoverable from subcommand help;
    common commands should also accept `--model`.

## Ideal First Five Minutes

```sh
cd ~/code/my-project
sac
```

Expected TTY journey:

```text
SafeCode Agent v4.16 - local, safety-first coding assistant.
No provider configured. Let's set one up. Ctrl-C cancels.

Provider:
  deepseek    fast daily default
  openai      OpenAI models
  anthropic   Claude models
  mock        deterministic, no network

Credential:
  use $DEEPSEEK_API_KEY if present
  store in keychain
  skip for now

Ready: deepseek / flash / api.deepseek.com only

sac> /ask what does this project do?
sac> /model pro
sac> /fix
```

The five-minute target is that a user with an installed CLI, an API key in the
environment or pasted once, and a real project should not need documentation
before reaching a working prompt.

## Version Plan

| Version | Theme | User-facing Goal | Risk |
| --- | --- | --- | --- |
| `v4.14.1` | First-run diagnostic clarity | `sac doctor` and `sac provider status` show top-line verdicts and next commands | Low |
| `v4.14.2` | One-shot `--model` parity | common subcommands accept `--model`; root override remains | Low |
| `v4.15.0` | `sac init` front door | one guided provider/key/policy setup path replaces scattered quickstarts | Medium |
| `v4.15.1` | Session-scoped model switching | `/model` and `sac model` are session-only by default; `--save` persists | Medium |
| `v4.15.2` | Keychain and env-only credentials | provider setup defaults away from plaintext user-config secrets | Medium |
| `v4.16.0` | Bare `sac` enters shell | TTY `sac` starts the interactive shell; root help is trimmed | High |
| `v4.16.1` | Config migration and audit | legacy `[llm]` migrates to provider profiles with backup and precedence trace | Low-Medium |
| `v4.16.2` | Error-message rewrite | failure messages consistently answer "what happened" and "what next" | Low |

## Acceptance Criteria

### v4.14.1 - First-run Diagnostic Clarity

- `sac doctor` prints `Overall: READY` or `Overall: NEEDS SETUP - N issue(s)`
  before the diagnostic table.
- Every failed doctor row includes a `Next:` field with a concrete command.
- `sac provider status` starts with a one-line verdict and moves raw details
  under a `Details:` block.
- `sac quickstart` does not recommend a live-provider demo when the effective
  provider/key/network state is not ready.
- Tests cover doctor verdicts, provider status verdicts, and quickstart
  provider-not-ready behavior.
- Docs update troubleshooting examples; public contracts remain unchanged.

### v4.14.2 - One-shot `--model` Parity

- `sac ask`, `sac edit`, `sac fix`, `sac run`, `sac shell`, and
  `sac agent run` accept `--model <alias-or-id>`.
- A subcommand-level `--model` wins over root `sac --model`.
- Help text for each supported subcommand documents `--model`.
- No config writes, audit schema changes, or stable-contract changes.

### v4.15.0 - `sac init`

- `sac init` is interactive in TTY mode and prints a static non-TTY template
  with equivalent flags.
- The flow covers provider choice, key source, default model, policy preset,
  and network allowlist confirmation.
- It refuses to lower user-level policy from a project directory.
- `sac setup --wizard` and `sac provider add` remain callable but are no longer
  the recommended first-run path.
- README and MVP guide quickstarts lead with `sac init`.

### v4.15.1 - Session-scoped Model Switching

- `sac model <alias>` and shell `/model <alias>` change the current session by
  default and write nothing.
- `sac model --save <alias>` and `/model save <alias>` persist to the trusted
  user config.
- Output always states `session-only` or `saved globally`.
- A one-minor compatibility flag may preserve legacy global persistence, with a
  deprecation warning.
- Tests cover no-write session changes, saved changes, shell behavior, and
  legacy-flag behavior.

### v4.15.2 - Keychain and Env-only Credentials

- `sac provider add` prefers env-var or keychain storage.
- Literal `--api-key` persistence requires an explicit storage choice such as
  `--store user-config` or `--store keychain`.
- `sac doctor` reports `credential_storage: env | keychain | user-config |
  missing`.
- `sac provider rm` removes matching keychain entries when present.
- Existing user-config keys remain readable and get a migration hint.
- Tests use a mocked keyring backend and assert no secret leakage in doctor,
  smoke, audit, or error output.

### v4.16.0 - Bare `sac` Enters the Shell

- TTY plus no subcommand enters the existing shell loop.
- Non-TTY plus no subcommand keeps the current help behavior.
- User config supports an opt-out flag for one minor release.
- `sac --help` trims to the daily first-run surface; advanced commands remain
  callable and move to `sac help all`.
- Shell `/help` becomes the canonical discovery surface for slash commands.
- Tests cover TTY/non-TTY default behavior and help-surface trimming.

### v4.16.1 - Config Migration and Audit

- `sac config migrate` converts legacy `[llm]` settings into
  `[providers.<name>]` with a backup file.
- Migration never prints secrets and never weakens user-level safety or network
  policy.
- `sac doctor` warns when legacy `[llm]` is still authoritative or conflicting.
- `sac provider status` shows a precedence trace:
  env > active provider profile > legacy `[llm]` > defaults.

### v4.16.2 - Error-message Rewrite

- Common provider/model/network failures all include:
  `Problem:`, `Why:`, and `Next:`.
- The runtime failure taxonomy maps each category to one user-facing next
  command.
- `sac why` or an equivalent alias can summarize the last failure by category
  and next command, reusing `sac debug last-failure` data.
- Tests pin representative messages while avoiding brittle full-output
  snapshots.

## Safety Invariants

- Project config cannot store credentials.
- Project config cannot silently widen user-level network policy.
- Model/provider changes must state whether they are session-only or persisted.
- Live-provider smoke remains opt-in.
- Mutating actions still stop at review/apply/commit approval boundaries.
- Public contract status remains unchanged unless a separate contract review
  promotes a surface.
