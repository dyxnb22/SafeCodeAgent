# Post-v4.16 Shell & Interaction UX Roadmap

Status: COMPLETED as of v4.18.1 (2026-06-06).
Baseline: `v4.16.2` error-message rewrite + 7-command help surface.
Created: 2026-06-05.

## Goal

Close the remaining interaction-quality gap between SafeCode Agent and
Claude Code / Reasonix / DeepSeek TUI without weakening SafeCode's safety
posture: no auto-apply, no auto-commit, no project-local credentials, and
approval-gated mutation paths.

The v4.14–v4.16 train closed the *first-run* and *surface-level* gaps
(bare sac → shell, unified init, session model, keychain, 7-command
help). What remains is the *feel* of daily use: streaming, shell polish,
diff rendering, undo granularity, and smarter diagnostics.

## Non-Goals

- No auto-apply, auto-commit, push, PR, background task, RAG, embeddings,
  LangGraph, or cloud execution.
- No stable-contract promotion.
- No project-local credential storage.
- No hidden weakening of user-level network or safety policy.
- No architectural refactors orthogonal to UX.

## Remaining UX Gaps (ordered by user impact)

### 1. Streaming output (HIGH)

**Current:** `sac ask`, `sac shell`, and `sac edit` return responses
batch-style — the user waits for the full LLM reply before seeing any
output.

**Claude Code / DeepSeek TUI:** Token-by-token real-time streaming with
incremental rendering. Users see the response build, which dramatically
improves perceived latency and UX even when total wall-clock time is
similar.

**Gap:** The LLM layer already has `stream_chat()` via `SupportsStreaming`
Protocol (v3.2.1), including SSE parsing and `StreamChunk` aggregation.
The CLI shell just doesn't wire it to the console.

**Proposed:**
- `sac ask --stream` / `sac shell` default streamed output via Rich Live.
- Non-TTY fallback to batch (unchanged).
- Token-level redaction during streaming.
- No change to safety gates — streaming is a rendering choice, not a
  policy change.

### 2. Shell interaction polish (HIGH)

**Current:** `sac shell` uses base readline. No syntax highlighting in
responses, no history search, no tab completion for slash commands.

**Proposed (v4.17.x):**
- Rich Markdown rendering for LLM responses (code blocks, tables, inline
  emphasis).
- Syntax-highlighted diff blocks in shell output (reuse existing
  `rich.Syntax("diff", ...)` from `sac apply`).
- Slash-command tab completion (readline `completer`).
- Deduplicated command history with Ctrl-R / ↑↓ search.
- `/clear` to reset context within a session.

### 3. Live connectivity diagnostics (MEDIUM)

**Current:** `sac doctor` only inspects config, env vars, and network
policy text. It never attempts a real API call, so "configured but
can't reach the endpoint" passes silently.

**Proposed (v4.17.x):**
- `sac doctor --live` attempts a lightweight GET/health ping to the
  configured provider base URL (with timeout, no auth needed).
- `sac provider status --live` does the same scoped to the active
  provider.
- Both respect `SAFECODE_DOCTOR_UPDATE_CHECK=0` for offline mode.
- Opt-in only; default `sac doctor` stays static (unchanged).

### 4. Levenshtein fuzzy matching for model/provider names (LOW)

**Current:** Typo suggestions for model aliases are four hardcoded
mappings (`deepseek-v4-falsh → flash` etc.). Unknown provider names
or model IDs with minor typos get generic error messages.

**Proposed (v4.17.x):**
- Compute Levenshtein distance against the known alias + provider name
  map.
- Suggest the closest match when distance ≤ 2.
- Applies to: `sac model`, `sac provider add`, `--model` flag, and
  shell `/model`.

### 5. Per-edit undo / checkpoint granularity (MEDIUM)

**Current:** `sac rollback --last` is a bulk checkpoint restore. Editing
three files and applying three patches then rolling back loses all three.
Claude Code supports per-edit undo in its diff view.

**Proposed (v4.18.x):**
- Per-patch checkpoint: `sac apply` records one checkpoint per
  patch file rather than one per apply invocation.
- `sac rollback --last` still works at apply level.
- New: `sac rollback --patch <id>` restores a single file to its
  pre-patch state.
- Does not change the hash-chain or audit model.

### 6. Diff rendering in shell (MEDIUM)

**Current:** `sac apply` shows a diff preview via `rich.Syntax(diff_text,
"diff", ...)` but `sac shell /apply` is text-only.

**Proposed (v4.17.x):**
- Shell `/apply` (and equivalent approval prompts) render diffs with
  Rich syntax highlighting.
- Consistent with the batch `sac apply` UX.

### 7. Agent-loop transparency (LOW)

**Current:** `sac shell --agentic` and `sac agent run` execute multi-step
loops without showing intermediate tool-intent decisions.

**Proposed (v4.18.x):**
- Rich `Status` panel in agentic shell mode showing current step,
  tool intent, and status.
- Non-blocking; togglable with `/verbose`.
- Reuses the existing `TypedAgentStep` / `TypedAgentStepResult` models
  from v4.11.

## Version Plan (tentative)

| Version   | Theme                              | Risk   |
|-----------|------------------------------------|--------|
| `v4.17.0` | Streaming output (ask + shell)     | Medium |
| `v4.17.1` | Shell polish (history, completer, Markdown) | Low |
| `v4.17.2` | Live connectivity (doctor --live)  | Low |
| `v4.17.3` | Levenshtein fuzzy matching         | Low |
| `v4.18.0` | Diff rendering in shell + per-patch undo | Medium |
| `v4.18.1` | Agent-loop transparency            | Low |

## Safety Invariants (unchanged)

- Streaming must redact secrets at the token level before rendering.
- Live connectivity pings use no authentication credentials.
- Per-patch checkpoints preserve existing hash-chain integrity.
- No command-authorisation gate is weakened.
- Project config cannot store credentials.
- Public contract status remains unchanged.
