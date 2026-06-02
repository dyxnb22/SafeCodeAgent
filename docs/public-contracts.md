# SafeCode Agent v3.0 Public Contracts

This document describes the local safety contracts that are stable in v3.0 and the surfaces
that remain explicitly experimental. Build workflows on top of the stable contracts. Do not
rely on experimental surfaces for automation; they may change without a major version bump.

## Stable Contracts

### 1. Config Precedence and Lowering Rules

**Where:** `src/safecode/config.py`, `SafeCodeConfig` and sub-models.

**Contract:** Configuration is loaded in order: user config → project config → env vars.
A project-local config is never allowed to lower user-level safety policy:

- `shell.block_high_risk` cannot be set to `false` when the user config has it `true`.
- `sandbox.restrict_to_project_root` cannot be set to `false` when the user config has it `true`.
- `sandbox.network_enabled` cannot be enabled by project config when the user has it disabled.
- Unknown policy names in project config are treated conservatively (balanced precedence).
- An unknown `SAFECODE_POLICY` env var value is ignored with a `UserWarning`.

**Snapshot:** `tests/snapshots/contracts/config_defaults.json`

**Known policy names:** `strict`, `balanced`, `experimental`, `normal` (alias for balanced),
`learning` (alias for experimental).

---

### 2. Pending Patch Format

**Where:** `src/safecode/patch/models.py`, `PatchProposal`, `PatchBlock`.

**Contract:** A pending patch is a JSON file saved inside `sac_dir` before the user approves
any file write. It is removed after `apply` or on rollback.

**`PatchProposal` fields:** `id`, `task`, `blocks`, `created_at`, `model`, `status`.

**`PatchBlock` fields:** `operation`, `file_path`, `search`, `replace`, `content`.

**`status` values:** `pending`, `applied`, `rejected`.

**Snapshot:** `tests/snapshots/contracts/pending_patch_schema.json`

---

### 3. Audit Event Hash-Chain Behavior

**Where:** `src/safecode/audit/logger.py`, `src/safecode/audit/models.py`,
`src/safecode/audit/anchor.py`.

**Contract:** Every write operation produces an `AuditEvent` appended to an append-only JSONL
log at `sac_dir/logs/events.jsonl`. Each event carries:

- `event_hash`: SHA-256 of the event JSON with `event_hash` set to `null` (keys sorted).
- `previous_hash`: the `event_hash` of the prior event; `null` for the first event.

The `AuditAnchorStore` writes `line_count` and the latest `event_hash` outside the project
root. A non-empty audit log without an anchor is treated as an integrity failure.

**`AuditEvent` fields:** `checkpoint_id`, `command`, `error`, `event_hash`, `exit_code`,
`files`, `message`, `metadata`, `patch_id`, `previous_hash`, `status`, `timestamp`,
`trace_id`, `type`.

**Snapshot:** `tests/snapshots/contracts/audit_event_schema.json`

---

### 4. Sandbox Approval and Result Lifecycle

**Where:** `src/safecode/sandbox/execution.py`, `src/safecode/sandbox/approvals.py`.

**Contract:** The full lifecycle is:
`propose → preflight → approve (user-level, single-use, atomic) → execute → result_record`

- **SandboxExecutionProposal**: written to `sac_dir`; describes the pending command, backend,
  hashes, and network/filesystem policy.
- **SandboxExecutionApproval**: written outside the project root; bound to project key, backend,
  command hash, and preview hash. Single-use — consumed atomically on claim.
- **SandboxExecutionResultRecord**: written per attempt; contains truncated/redacted output.

Approval invariants:
- Approvals are single-use (consumed flag set after claim).
- Approvals are project-bound (project_key derived from project root).
- Approval files live outside the project root.
- Claim uses lock file and `os.replace` for atomicity.
- Expired approvals are treated as unapproved.

**Snapshot:** `tests/snapshots/contracts/sandbox_schemas.json`

---

### 5. Local Tool Registry Shape

**Where:** `src/safecode/tools/registry.py`, `ToolSpec`, `ToolRegistry`.

**Contract:** The local ToolSpec registry is a deterministic, keyless list of `ToolSpec` objects.
Each spec carries: `name`, `version`, `description`, `risk`, `permission_category`,
`requires_human_approval`, `args`, and `audit_event`.

Safety invariants enforced by tests:
- High-risk tools must have `requires_human_approval=True`.
- WRITE and SHELL permission tools must have `requires_human_approval=True`.
- All registered tools have a non-empty `version` string.
- `REGISTRY_SCHEMA_VERSION` is a numeric string; increment it when schema fields change.

**Snapshot:** `tests/snapshots/registry/tool_registry_v1.json`

---

### 6. Deterministic Eval Trace Format

**Where:** `src/safecode/eval/loop_runner.py`, `LoopStepTrace`, `LoopEvalTrace`,
`build_loop_eval_trace()`.

**Contract:** `build_loop_eval_trace(fixture)` produces a `LoopEvalTrace` deterministically
from the fixture definition alone — no LLM calls, no timestamps, no absolute paths.

- **`LoopStepTrace` fields:** `step_index`, `tool_intent_type`, `tool_intent_target`,
  `is_stop_for_user`, `is_first_fail_recoverable`.
- **`LoopEvalTrace` fields:** `fixture_name`, `steps`, `expected_pending_patch`, `patch_hash`.

`patch_hash` is the SHA-256 of `expected_patch_contains` fragments joined. `as_dict()` is
JSON-serializable and byte-stable across runs.

**Snapshot:** `tests/snapshots/contracts/eval_trace_schema.json`
**Per-fixture snapshots:** `tests/snapshots/loop/*.json`

---

### 7. Recommended CLI Workflows

The daily-use commands are visible in `sac --help`:

```
sac setup           # first-time: write .sac/config.toml
sac quickstart      # guided first-run: check config, show demo, print next steps
sac ask             # ask a read-only question about the project
sac edit            # propose a patch; stops before applying
sac apply           # apply an approved pending patch
sac rollback        # restore from the latest checkpoint
sac run             # run an approved, policy-classified shell command
sac doctor          # runtime health check
sac version         # display installed version
```

For release workflows:

```
sac release preflight   # final local release gate (aggregates check/smoke/meta/docs)
sac release bump        # update version in pyproject.toml and __init__.py
sac release changelog   # render Markdown changelog from version notes
```

---

### 8. Hidden/Internal Release Command Policy

The following commands are callable but hidden from `sac release --help`:

```
sac release signoff     # [deprecated] use sac release preflight instead
sac release checklist   # [planning helper] not a release gate
sac release check       # lower-level check (aggregated by preflight)
sac release smoke       # lower-level smoke (aggregated by preflight)
sac release meta        # lower-level metadata audit (aggregated by preflight)
```

These helpers are preserved for backward compatibility but are not part of the recommended
release workflow. The recommended release sequence is:
`bump → pytest → commit → tag → preflight`.

---

### 9. LLM Provider Contract

**Where:** `src/safecode/llm/`, `src/safecode/config.py` (`LLMConfig`).

**Full reference:** [docs/providers.md](providers.md)

**Contract:** The LLM provider layer has a stable set of semantics around provider
selection, retry, structured-output validation, streaming, cost accounting, and
fan-out routing.

**Supported provider keys:** `mock`, `openai`, `openai-compatible`, `anthropic`.

**`LLMConfig` fields:** `provider`, `model`, `base_url`, `fallback_provider`,
`fallback_model`, `fallback_base_url`.

**Retry invariants:**
- HTTP 429 and 503 are retried with bounded jitter; `URLError` is also retried.
- Other 4xx/5xx, policy blocks (`PermissionError`), contract violations (`ValueError`),
  and `RecoverableContractFailure` values are never retried.

**Structured-output validation invariants:**
- `validate_provider_json()` returns `RecoverableContractFailure` for soft parse failures.
- Hard contract violations raise `ValueError` (fail-closed).
- `parse_agent_contract_response()` is unchanged for non-provider paths.

**Fan-out invariants:**
- Only `RuntimeError` (transport failure) triggers fallback routing.
- `PermissionError` (network policy) is never routed around.
- `RecoverableContractFailure` (returned value) is not a trigger for fallback.
- Fan-out log is redacted — no prompt or context content.

**Streaming invariants:**
- `StreamError` is raised on hard stream failures; partial output is discarded.
- Cancellation must not mutate session cost state.

**Snapshot:** `tests/snapshots/contracts/provider_contract_schema.json`

---

## Experimental Surfaces

The following are explicitly experimental in v3.0. They may change, be removed, or be
promoted to stable contracts in a future release.

| Surface | Why experimental |
|---|---|
| `SafeCodeLocalAPI` beyond `ask()` and `report()` | Not yet snapshot-tested or versioned |
| OpenAI-compatible live provider behavior | Depends on network and API key; not deterministic |
| MCP schema shim | Keyword-based classification fallback; no real JSON-RPC client |
| Subagent payload evolution beyond read-only bounded findings | Payload versioning is v1 only |
| TUI (`sac tui dashboard`) | Rich rendering; not yet stable |
| IDE bridge (`sac ide ...`) | Early manifest; subject to change |

## Contract Test Coverage

All stable contracts are snapshot-tested in `tests/test_public_contract_snapshots.py`.
The tool registry is additionally snapshot-tested in `tests/test_tool_schema_registry.py`.

Run contract snapshot tests:

```bash
PYTHONPATH=src python3 -m pytest tests/test_public_contract_snapshots.py -q
```
