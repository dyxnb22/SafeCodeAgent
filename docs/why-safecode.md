# Why SafeCode Agent?

SafeCode Agent is a safety-first local coding agent designed for developers
who want AI-assisted editing with explicit, auditable control over every write.

## The Core Problem

Most AI coding tools operate as a black box: you give them a goal and they
modify your files. If something goes wrong, you rely on `git` to recover.
SafeCode Agent takes a different approach: every write goes through a visible,
human-approved gate before it is applied.

## The Safety Loop

SafeCode's core loop is designed so that every meaningful side effect is
visible before it happens:

```text
collect context
-> propose patch
-> preview diff      ← you see exactly what will change
-> human approval    ← nothing writes until you say so
-> checkpoint        ← rollback point written before apply
-> apply patch
-> audit log         ← immutable, hash-chained record
-> rollback          ← always available
```

No file is written without a preview. No write happens without a checkpoint.
Every write produces an audit event you can inspect.

## Key Properties

**Explicit approval.** Patches are proposed and shown as diffs. You approve or
reject. `sac apply` is a separate command from `sac edit`.

**Checkpoint before every write.** A rollback point is captured before any
file is modified. `sac rollback --last` always works.

**Audit trail.** Every write, command, and decision is appended to an
append-only audit log with SHA-256 hash chaining. The anchor lives outside the
project root so it cannot be tampered with by project-controlled files.

**Policy-gated shell.** Shell commands are classified by risk. High-risk
commands are blocked even with `--yes`. Commands run through argv execution,
not a shell string — no shell injection from model output.

**Project config cannot lower user safety.** If you set `block_high_risk =
true` in your user config, a project's `.sac/config.toml` cannot unset it.
Network access disabled in user config stays disabled in all projects.

**Bounded context collection.** The agent collects only file content it needs,
skips secret-like filenames (`.env*`, `*token*`, `*secret*`), and redacts
secrets from context before sending to the LLM.

## What SafeCode Is Not

- **Not a replacement for `git`.** SafeCode adds approval and audit on top of
  your existing workflow. Use `git` for branching and history; use SafeCode for
  controlled AI-assisted edits within a branch.

- **Not a fully autonomous agent.** The default mode requires human approval
  before each write. Autopilot mode reduces prompts but does not eliminate the
  audit gate.

- **Not a sandbox guarantee.** The Noop backend enforces SafeCode's logical
  gates but does not provide OS-level containment. Docker, macOS Seatbelt, and
  Linux Bubblewrap backends add containment but remain in preview.

- **Not a network proxy.** Network access is disabled by default. SafeCode does
  not intercept or proxy your outbound traffic.

## Comparison

Claims here are limited to observable behaviours described in
[docs/public-contracts.md](public-contracts.md) and tested in the test suite.

| Aspect | Raw LLM | SafeCode Agent |
|--------|---------|----------------|
| Diff preview | Manual copy-paste | Rich per-file panels before apply |
| Write gate | None | Explicit `sac apply` or tier-gated auto-apply |
| Rollback | `git checkout` | `sac rollback --last` or session rollback |
| Audit log | None | Append-only JSONL with hash chain |
| Context control | Manual | Budget-limited, secret-filtered, git-aware |
| Shell execution | None | Policy-gated, risk-classified |

Compared with fully autonomous agents, SafeCode optimizes for control:
`--full-auto` reduces stops for lower-risk tiers, but GATE-tier operations such
as delete, shell, network, push, and `.env` access still stop for review. The
audit log records both manual approvals and auto-approvals.

Compared with git-only workflows, SafeCode creates a checkpoint before the
write and records why the agent wanted the change. Use both: git for branch and
project history, SafeCode for controlled AI-assisted edits within a branch.

Compared with editor extensions, SafeCode keeps the approval loop in the
terminal and applies the same checkpoint/audit path regardless of which editor
you use.

## Capability Summary

| Capability | Status |
|-----------|--------|
| Diff preview before write | Stable |
| Explicit write gate (`sac apply`) | Stable |
| Rollback (`sac rollback --last`) | Stable |
| Append-only audit log (hash-chain) | Stable |
| Policy-gated shell execution | Stable |
| Config precedence (project cannot lower user safety) | Stable |
| Conversation-backed agentic shell (`sac shell --agentic`) | Experimental |
| Plan / Build shell mode (`--mode plan\|build`) | Experimental |
| Approval tiers (`auto` / `confirm` / `gate`) | Experimental |
| Global symbol search (`search_symbol`, ripgrep + AST) | Stable |
| Sandbox planning (Docker, Seatbelt, Bubblewrap) | Preview |
| MCP read-only execution | Stable |
| MCP write proposals | Experimental |

## Experimental Surfaces

The following capabilities are explicitly experimental as of v3.6:

- **SafeCodeLocalAPI** (beyond `ask` and `report`): the JSON-RPC bridge is
  usable but the method set and wire format may change.
- **MCP server integration**: stdio transport, discovery, and read-only
  execution are experimental; write promotion requires explicit approval
  and remains a proposal surface only.
- **Subagent v2 payloads**: the v2 payload schema is stable but future
  fields are not yet committed.
- **TUI** (`sac tui interactive`): functional but not a stable CLI contract.
- **IDE bridge** (`sac api jsonrpc`): usable from VS Code extension stubs but
  the protocol contract is not yet frozen.

See [docs/public-contracts.md](public-contracts.md) for the full list of
stable versus experimental surfaces.

## Getting Started

```bash
uv sync
uv run sac quickstart   # guided first-run
uv run sac doctor       # check your setup
```

See [docs/user-guide.md](user-guide.md) for a complete walkthrough.
