# SafeCode Agent Context Budgets

This document describes the context-packing budget system used by SafeCode Agent
to control how much source content is passed to the LLM on each request.

---

## Overview

The context budget limits how many bytes of project context are packed per LLM
call. The default budget is **40,000 characters** (approximately 10,000 tokens at
a 4-char-per-token estimate). This limit is enforced by `ContextBudgetPacker`
in `src/safecode/context/budget.py`.

Budget configuration lives in `SafeCodeConfig.max_context_chars` (default 40,000).
Project-local config can only *lower* this limit, not raise it above the user-level
setting.

---

## Core Classes

| Class | Location | Role |
|---|---|---|
| `ContextBudget` | `src/safecode/context/budget.py` | Byte and token limits for one pack call |
| `ContextBudgetPacker` | `src/safecode/context/budget.py` | Packs context dict within budget; truncates oversized fields |
| `ContextBudgetReport` | `src/safecode/context/budget.py` | Summary of bytes used, tokens estimated, truncation decisions |
| `ContextSource` | `src/safecode/context/budget.py` | Per-field metadata: key, kind, bytes, truncated flag |

---

## Default Budget

```
max_context_chars = 40_000   # ≈ 40 KB of text
max_tokens ≈ 10_000          # 40_000 / TOKEN_CHAR_RATIO (4)
```

Override in `.sac/config.toml`:

```toml
[context]
max_context_chars = 20000   # lower limit; cannot exceed user-level setting
```

---

## p50 Context-Pack Budget by Language Preset

The numbers below are **baseline fixture-derived**: measured from the six scripted
eval fixtures in `tests/snapshots/bench/` (written by `sac eval bench` on first
run). These fixtures are small synthetic tasks, not real project codebases, so
actual production context sizes will be larger.

| Language / Preset | Fixture | p50 step count | p50 patch hash stable? |
|---|---|---|---|
| Python (function fix) | `python-function-fix` | 2 | yes (scripted) |
| Python (config update) | `config-update-fix` | 2 | yes (scripted) |
| Docs (any stack) | `docs-edit` | 2 | yes (scripted) |
| Shell / read-only | `shell-readonly-check` | 2 | yes (scripted) |
| Python (test assertion) | `test-assertion-fix` | 2 | yes (scripted) |
| Python (import cleanup) | `import-cleanup` | 2 | yes (scripted) |

**Note**: p50 step counts are 2 for all scripted fixtures (one tool intent + one
stop-for-user step). Real-world tasks may use more steps. Patch hash stability
is guaranteed for scripted fixtures because the LLM client is mocked — the same
fixture always produces the same patch.

### Reproducing these numbers

```sh
# Write or refresh bench snapshots
PYTHONPATH=src python3 -m safecode.cli eval --mode bench
# View snapshot for one fixture
cat tests/snapshots/bench/python-function-fix.json
```

---

## Context Packing Behavior

1. The collector calls `ContextBudgetPacker.pack(context)` after gathering sources.
2. String values are truncated to fit the remaining budget.
3. File lists are truncated entry-by-entry; earlier entries take priority.
4. Non-string, non-file-list values pass through unchanged.
5. Truncation is logged in `ContextBudgetReport.truncation_notes`.
6. The packer never raises; it returns whatever fits.

---

## Safety Notes

- Budget enforcement happens at context collection time, before the LLM call.
- Project config can only lower the budget via `SafeCodeConfig.merge_trusted_config()`.
- The `TOKEN_CHAR_RATIO = 4` is a conservative estimate; actual tokens may be fewer.
- No context content is written to `.sac/metrics.jsonl`; only byte counts are stored
  when metrics are enabled.
