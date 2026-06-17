# SafeCode Agent vs. Other Approaches

Claims here are limited to observable behaviours described in
[docs/public-contracts.md](public-contracts.md) and tested in the test suite.

---

## vs. Running an LLM Directly

Raw LLM output requires manual copy-paste, manual apply, manual rollback.

| Aspect | Raw LLM | SafeCode Agent |
|--------|---------|----------------|
| Diff preview | Manual copy-paste | Rich per-file panels before apply |
| Write gate | None | Explicit `sac apply` or tier-gated auto-apply |
| Rollback | `git checkout` | `sac rollback --last` (SHA-256 checkpoint before write) |
| Audit log | None | Append-only JSONL with hash chain |
| Context control | Manual | Budget-limited, secret-filtered, git-aware |
| Shell execution | None | Policy-gated, risk-classified |
| Secret guard | None | Redaction before LLM call and before disk write |

---

## vs. Fully Autonomous Agents

Autonomous agents optimize for speed. SafeCode optimizes for control.

- Every write stops for approval by default.
- `--full-auto` reduces stops (applies AUTO and CONFIRM tier automatically) but keeps the gate for GATE-tier operations (delete, shell, network, push, `.env`).
- The audit log records every decision including auto-approvals.
- `/undo` and `sac rollback` are always available.

---

## vs. Git-Based Approaches

`git` records history **after the fact**. SafeCode adds a checkpoint **before** the write.

| Aspect | Git only | SafeCode + Git |
|--------|----------|----------------|
| Pre-write checkpoint | Manual stash/branch | Automatic SHA-256 backup |
| Rollback | `git checkout` / `git revert` | `sac rollback --last` |
| AI decision audit | None | Hash-chained audit log |
| Dirty-tree protection | None | Blocks silent overwrite of uncommitted user changes |

Use both. SafeCode does not replace `git`.

---

## vs. Editor Extensions (Copilot, Cursor, etc.)

Editor extensions apply changes directly inside the editor buffer, often without an intermediate approval step.

SafeCode is terminal-first:
- Approval loop is in the terminal, not the editor.
- Every write creates a checkpoint, regardless of where the agent runs.
- The IDE bridge (`sac api jsonrpc`) lets an editor call SafeCode for proposals — the approval gate remains SafeCode's.

---

## vs. opencode

opencode is an open-source multi-model terminal agent with Plan/Act modes.

| Feature | SafeCode Agent | opencode |
|---|---|---|
| File write safety | Approval gate + checkpoint + audit (structural) | Auto or prompted |
| Rollback | Per-write checkpoint; session rollback atomic | Not documented |
| Audit trail | SHA-256 hash-chain JSONL; tamper-evident | Not documented |
| Dirty-tree guard | Explicit: blocks overwrite of user's uncommitted changes | Not documented |
| Context compaction | LLM-generated structured summary at turn 12+; archives raw observations | `/compact` |
| Symbol search | `search_symbol` ripgrep+AST; `find_references` Jedi (Python); `grep_files` | Built-in tools |
| Plan / Build mode | `--mode plan` (read-only tools only) / `--mode build` | Plan / Act |
| Approval tiers | `auto` / `confirm` / `gate` — configurable thresholds | Trust mode |
| MCP | Read bridge + single-use write approval; write never auto-executes | Plugin system |
| Offline / keyless | Full mock mode; all 6000+ tests pass with no API key | Requires provider key |
| Live eval | 28 inline fixtures; 91.8% (78/85) with DeepSeek v4-flash | Not documented |
| Commit message | `sac commit --ai` generates conventional-commit via LLM | Not documented |

**SafeCode's structural advantages** (enforced in Python, not by prompt):
1. `ToolCallGate` cannot be bypassed by model output — it's a Python function not a prompt instruction.
2. Dirty-tree guard prevents the agent from silently overwriting your in-progress work.
3. Audit anchors stored outside the project root — a compromised project cannot tamper with the log.
4. Project-local config **cannot lower** user-level safety policy — an untrusted `.sac/config.toml` cannot grant more permissions than the user allows.

---

## Capability Summary (v6.28)

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
| LLM-backed context compaction (turn 12+ summary) | Experimental |
| Global symbol search (`search_symbol`, ripgrep + AST) | Experimental |
| Multi-file auto-apply in `--full-auto` (CONFIRM tier) | Experimental |
| Rich per-file diff rendering | Experimental |
| AI commit message (`sac commit --ai`) | Experimental |
| Semantic Python references + rename | Experimental |
| Terminal LSP diagnostics (`sac lsp diagnostics`) | Experimental |
| Diagnostics-aware repair loop | Experimental |
| Test generation (`sac test-gen generate`) | Experimental |
| Formatter integration (`sac format run`) | Experimental |
| Session management (`sac session list/stats/export`) | Experimental |
| User-declared tool metadata (`.sac/tools.toml`) | Experimental |
| Step journal for long-task resume | Experimental |
| Git-aware context + dirty-tree guard | Experimental |
| Sandbox planning (Docker, Seatbelt, Bubblewrap) | Preview |
| MCP read-only execution | Experimental |
| MCP write proposals | Experimental |
| LocalAPI JSON-RPC bridge | Experimental |
| OTel event export | Experimental |

**Stable** = contract documented in [docs/public-contracts.md](public-contracts.md), protected by snapshot tests.  
**Preview** = functional, subject to change.  
**Experimental** = interface may change without major version bump.
