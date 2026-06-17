# SafeCode Agent vs. Other Approaches

This document compares SafeCode Agent to related tools and approaches.
Claims here are limited to observable behaviors described in
[docs/public-contracts.md](public-contracts.md) and tested in the test suite.

---

## vs. Running an LLM Directly (API or Chat)

Running a model directly gives you raw output. You copy-paste diffs manually,
apply them with your editor, and decide when to commit.

SafeCode wraps the same LLM calls in a controlled pipeline:

| Aspect | Raw LLM | SafeCode Agent |
|--------|---------|----------------|
| Diff preview | Manual copy-paste | Rendered before apply |
| Write gate | None | Explicit `sac apply` |
| Rollback | `git checkout` | `sac rollback --last` (checkpoint before write) |
| Audit log | None | Append-only JSONL with hash chain |
| Context control | Manual | Budget-limited, secret-filtered |
| Shell execution | None | Policy-gated, risk-classified |

SafeCode does not eliminate the need for `git`; it adds explicit gating and
audit on top of your existing workflow.

---

## vs. Fully Autonomous Agents

Autonomous agents (agents that edit files and run commands without stopping for
approval) optimize for speed. SafeCode optimizes for control.

The tradeoff is explicit:

- SafeCode requires approval before each write. You see every diff.
- Autopilot mode (`sac agent run`) reduces prompts but does not eliminate the
  audit gate or rollback capability.
- The audit log records every decision, including skipped approvals.

If you need full autonomy, SafeCode is not the right tool. If you want to know
exactly what changed and why, SafeCode is designed for that.

---

## vs. Git-Based Approaches (patch series, branch-per-task)

`git` records history after the fact. SafeCode adds a pre-write checkpoint and
approval gate before history is made.

| Aspect | Git only | SafeCode + Git |
|--------|----------|----------------|
| Pre-write checkpoint | Requires manual stash/branch | Automatic before apply |
| Rollback | `git checkout`/`git revert` | `sac rollback --last` |
| Audit of AI decisions | None | Hash-chained audit log |
| Write gate | None | `sac apply` |

SafeCode does not replace `git`. Use both.

---

## vs. Editor Extensions (Copilot, Cursor, etc.)

Editor extensions provide inline suggestions and chat-driven edits inside the
editor. They typically apply changes directly without an intermediate approval
step.

SafeCode is a terminal-first agent with an explicit approval loop. It does not
integrate into your editor buffer. The IDE bridge (`sac api jsonrpc`) allows
an editor extension to call SafeCode for proposals, but the approval and write
gate remain in SafeCode's control.

**Experimental:** The IDE bridge is experimental in v3.6. The wire protocol and
supported methods may change. Do not build production automation on top of it.

---

## Capability Summary (v6.23 dev)

| Capability | Status |
|-----------|--------|
| Diff preview before write | Stable |
| Explicit write gate (`sac apply`) | Stable |
| Rollback (`sac rollback --last`) | Stable |
| Append-only audit log | Stable |
| Policy-gated shell execution | Stable |
| Config precedence (project cannot lower user safety) | Stable |
| Conversation-backed agentic shell | Experimental |
| Plan/Build shell mode | Experimental |
| Semantic Python references and rename | Experimental |
| Terminal LSP diagnostics | Experimental |
| Session list/stats/export/import | Experimental |
| Formatter workflow | Experimental |
| User-declared tool metadata | Experimental |
| Sandbox planning (Docker, Seatbelt, Bubblewrap) | Preview |
| MCP read-only execution | Experimental |
| MCP write proposals | Experimental |
| LocalAPI JSON-RPC bridge | Experimental |
| TUI interactive view | Experimental |
| IDE bridge | Experimental |
| OTel event export | Experimental |

"Stable" means the contract, field names, and invariants are documented in
[docs/public-contracts.md](public-contracts.md) and protected by snapshot
tests. "Preview" means functional but subject to change. "Experimental" means
the interface may change without a major version bump.
