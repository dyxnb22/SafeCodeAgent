# SafeCode Agent Public Contracts

This document describes the local safety contracts that are stable through
v4.0.0 and the surfaces that remain explicitly experimental. Build workflows on
top of the stable contracts. Do not rely on experimental surfaces for
automation; they may change without a major version bump.

## v4.0.0 Contract Cut

v4.0.0 is a contract cut, not a runtime feature release.

- **New stable contracts promoted at v4.0.0:** none.
- **Breaking changes to v3.0 public contracts:** zero.
- **Already-stable contracts preserved for v4.0.0:** CLI JSON envelope
  (stable since v3.7.2) and MCP read execution (stable since v3.8.2).
- **Deferred/rejected at v4.0.0:** IDE JSON-RPC, TUI interactive,
  `sac report html`, and sandbox real-execution opt-in.

## v4.x Series (v4.0–v4.8) Contract Summary

The v4.x shell-first train (v4.0–v4.8) is now complete. It added zero new stable
contracts. All new v4.1–v4.8 surfaces remain explicitly experimental:

- `sac task`, `sac status`, `sac profile`, `sac resume`, `sac commit`,
  `sac branch new`, `sac diff --task`, `sac memory`, `sac debug`,
  `sac audit query`, `sac smoke`.
- `.sac/tasks/`, `.sac/memory/`, `.sac/project_profile.json` file layouts.
- Failure category enumeration in runtime logs.
- Per-task budget configuration.
- `sac fix --watch` behavior.

The twelve stable contracts from v4.0.0 (sections 1–12 of this document) remain
stable and unchanged through v4.8.2. No deferred surface (IDE JSON-RPC, TUI,
HTML report, sandbox real-execution opt-in) was promoted in v4.x.

## v4.9.x AI Shell MVP Contract Summary

The v4.9.x AI shell train adds zero new stable contracts. All new v4.9 surfaces
are explicitly EXPERIMENTAL:

- `sac shell` — interactive AI shell REPL.
- `sac shell /overview` — bounded project context builder.
- `sac shell /status`, `/task`, `/apply`, `/commit`, `/debug` — slash commands.
- Natural-language intent router (routes to existing primitives).
- Shell session state under `.sac/shell/`.
- `sac smoke ai-shell` — deterministic AI shell smoke suite.

No v4.9 surface is a stable contract. v4.9 introduces no breaking changes to
v4.0 stable contracts. v4.9 does not schedule v5. All twelve stable contracts
from v4.0.0 remain unchanged through v4.9.3.

## v4.10-v4.12 Resume-MVP Contract Summary

The v4.10-v4.12 resume-MVP train adds zero new stable contracts. All new
surfaces remain explicitly EXPERIMENTAL:

- DeepSeek provider preset and live-provider smoke.
- Agentic typed step, validation, resume, and smoke surfaces.
- `sac agent run` and `sac shell --agentic` behavior.
- `sac demo agent-loop`, `examples/fastapi-todo/`, and recorded demo transcript.

No v4.10-v4.12 surface is a stable contract. The train preserves approval,
checkpoint, audit, rollback, policy, dirty-tree, and network gates. It does
not add auto-apply, auto-commit, push, pull request automation, RAG,
embeddings, LangGraph, IDE requirements, cloud tasks, or background execution.

## v5.0.0 Stable Contract Promotions

v5.0.0 is the first major version boundary since v4.0.0. The following surfaces
graduate from EXPERIMENTAL to **stable contracts** at v5.0.0:

### 13. Native Tool Schemas (v5.0.0)

**Promoted tools:** `read_file`, `list_files`, `search_files`, `grep_files`,
`edit_file`, `write_file`, `run_command`.

**Contract:** The `NativeToolSpec` shape — `name`, `description`,
`input_schema` (JSON Schema object), `requires_approval`, `audit_event_type` —
is now stable for the seven promoted tools. The `input_schema` properties
and `required` fields will not be removed or renamed without a v6 major bump.

**Stable invariants:**
- `read_file`, `list_files`, `search_files`, `grep_files`: `requires_approval=False`; auto-executed.
- `edit_file`, `write_file`: `requires_approval=True`; always paused for user approval; checkpoint created before mutation.
- `run_command`: `requires_approval=False`; high-risk patterns blocked by `ShellRunner`/`RiskClassifier`; `cwd` validated to project root.
- Path inputs validated against project root boundary; root escapes blocked.
- `redact_secrets()` applied to all tool outputs before model context.

**What is NOT stable in this contract:**
- `web_fetch`, `github_read_issue/pr/file`, `github_create_pr`, `github_push_branch` remain EXPERIMENTAL.
- `choose_tool_native()` LLM client internals (Anthropic/OpenAI wire format) remain EXPERIMENTAL.
- `NativeToolSpec.experimental` field itself is informational only.

**Source:** `src/safecode/agent/read_tools.py`, `write_tools.py`, `command_tool.py`

---

### 14. Audit Event Types for Native Tools (v5.0.0)

**Contract:** Three audit event type strings are now stable:
- `"tool_call_read"` — emitted for every `read_file`, `list_files`, `search_files`, `grep_files` call.
- `"tool_call_write"` — emitted for every `edit_file`, `write_file` call.
- `"tool_call_command"` — emitted for every `run_command` call.

These values may appear in `sac audit query --type <value>` and in
`.sac/logs/events.jsonl` `event_type` fields. They will not be renamed or
removed without a v6 major bump.

**Source:** `src/safecode/audit/logger.py`, `AuditEvent.event_type`

---

### 15. Write-Tool Checkpoint Rollback Contract (v5.0.0)

**Contract:** Every `edit_file` and `write_file` call creates a
`CheckpointRecord` before mutation. The rollback path (`sac rollback --last`,
`/undo` in shell) restores the backed-up files using `CheckpointManager._restore_checkpoint()`.

As of v4.25.0, backup files carry a `sha256` hash; `_restore_checkpoint()`
verifies integrity before restoring and raises `CheckpointIntegrityError` on
mismatch without touching target files.

This round-trip — write → checkpoint → rollback → original state — is now
stable. Write tools that bypass this checkpoint path would be a contract violation.

**Source:** `src/safecode/checkpoint/manager.py`

---

### 16. `sac shell` Loop Contract (v5.0.0)

**Contract:** The `sac shell` interactive loop exposes four stable slash commands:
- `/clear` — resets live agent session state (`AgentSessionStore.clear()`).
- `/undo` — triggers rollback of the most recent write-tool checkpoint.
- `/history` — shows current session's tool calls and observations.
- `/tools` — lists all registered `NativeToolSpec` names with approval flags.

The shell prompt format `sac[N]>` (where N is the turn counter) is stable.
EOF and Ctrl-D exit print `[exiting shell]` before returning.

**Not stable:** slash commands specific to GitHub/web tools, shell streaming
behavior, session state file layout under `.sac/shell/`.

**Source:** `src/safecode/cli_shell.py`

---

### 17. Sandbox Execution Contract (v5.7.1)

**Promoted surfaces:** `SandboxExecutionProposal`, `SandboxApproval`,
`SandboxResultRecord`, `SandboxExecutionRequest`, and the `SandboxExecutionGate`
claim-execute lifecycle.

**Contract:** The sandbox execution lifecycle — propose → approve → claim →
execute → result record — is now stable for the Docker, macOS Seatbelt, and
Linux Bubblewrap backends. The Noop backend remains the default and must be
explicitly overridden.

**Stable invariants:**
- Execution is always preceded by a proposal (`SandboxExecutionProposal`) and
  user approval (`SandboxApproval`).
- `claim_for_execution()` is atomic — once claimed, the approval cannot be
  replayed or re-granted.
- Execution requires a passing preflight record (`SandboxExecutionPreflight`)
  AND an explicit env gate (`SAFECODE_SANDBOX_DOCKER=1`,
  `SAFECODE_SANDBOX_SEATBELT=1`, `SAFECODE_SANDBOX_BUBBLEWRAP=1`).
- `--privileged` is never passed to Docker; `--network none` is the default.
- All subprocess execution uses `shell=False`.
- Preview hash verification (sha256 of the rebuilt argv/profile) blocks
  execution on mismatch.
- All failures return `executed=False` — the gate never raises.

**Related experimental surfaces (not promoted):**
- `SandboxExecutionPreflight` interaction modes: the preflight schema is stable
  but custom preflight hooks are experimental.
- Environment variable names for opt-in (`SAFECODE_SANDBOX_*`): stable for
  the three promoted backends; new backends may add new vars.

**Sources:**
- `src/safecode/sandbox/execution.py` (proposal, approval, result)
- `src/safecode/sandbox/gate.py` (claim-execute lifecycle)
- `src/safecode/sandbox/docker.py` (DockerExecutor)
- `src/safecode/sandbox/seatbelt.py` (MacOSSeatbeltExecutor)
- `src/safecode/sandbox/bubblewrap.py` (LinuxBubblewrapExecutor)

---

### What is NOT promoted at v5.0.0

The following surfaces remain EXPERIMENTAL and may change without a major bump:

- `web_fetch`, `github_read_issue`, `github_read_pr`, `github_read_file`,
  `github_create_pr`, `github_push_branch`
- Anthropic/OpenAI native tool-use client internals (`choose_tool_native()`)
- Any CLI subcommand outside the 17-command visible surface (`sac --help`)
- `.sac/tasks/`, `.sac/memory/`, `.sac/shell/` file layouts
- `sac task`, `sac status`, `sac profile`, `sac resume`, `sac commit`, `sac debug`
- Failure category enumeration, per-task budget, `sac fix --watch`
- Agentic typed steps, `sac agent run`

Zero breaking changes to the twelve v4.0.0 stable contracts (sections 1–12).

---

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

**`LLMConfig` fields:** `provider`, `model`, `base_url`, `api_key`, `fallback_provider`,
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

### 10. Subagent Dispatch Payload v2 Contract

**Where:** `src/safecode/subagents/payload.py`, `SubagentDispatchPayload`.

**Contract:** Subagent journal event payloads at `payload_version=2` are a supported
format as of v3.4.3. v1 payloads remain supported for backward compatibility.

**v1 fields (stable since v2.9.6):** `payload_version`, `task_id`, `summary`,
`observations`, `files_inspected`, `errors`, `blocked`, `success`.

**v2 fields (promoted at v3.4.3):** `synthesis_summary`, `synthesis_key_findings`,
`synthesis_risks`, `synthesis_source_task_ids`, `cancelled_task_ids`.

**Invariants:**
- Old journals without `payload_version` parse as v1 with safe defaults.
- `SUPPORTED_PAYLOAD_VERSIONS = frozenset({1, 2})`.
- Unsupported future versions emit `RuntimeWarning` and return `None` (fail closed).
- Malformed payload warnings do not include caller-supplied content or secrets.
- All v2 fields have safe defaults so v1 payloads load without errors.
- New journal events written with `CURRENT_PAYLOAD_VERSION=2`.

---

### 11. CLI JSON Envelope Contract

**Where:** `src/safecode/cli_shared_json.py`, `CLIJSONResponse`.

**Contract:** All `--json` CLI output is wrapped in a `CLIJSONResponse` envelope. Promoted to
stable contract at v3.7.2.

**Required fields (always present):**
- `command` — string: the CLI command name (e.g. `ask`, `edit`, `apply`, `fix`).
- `status` — string: one of `success`, `error`, `cancelled`, `pass`, `fail`.
- `data` — object: command-specific payload (never null, never a primitive).

**Optional field:**
- `error` — string: present only when non-null; **omitted** when null.

**Output format:** sorted keys, `indent=2`, UTF-8. Callers should use
`"error" in json.loads(output)` to test for errors.

**Invariants:**
- `error` is omitted from serialized JSON when the response has no error.
- `data` is always a JSON object (never a list or scalar).
- Output is deterministic for the same inputs (no timestamps, no random ids).

**Snapshot:** `tests/snapshots/contracts/cli_json_envelope.json`

---

### 12. MCP Read Execution Contract

**Where:** `src/safecode/mcp/runner.py`, `MCPReadOnlyRunner.call_readonly`.

**Contract:** Read-only MCP tool execution has a stable gate sequence and result shape.
Promoted to stable contract at v3.8.2.  **MCP write execution and lifecycle remain experimental.**

**Result type:** `MCPRunResult` — fields: `server`, `tool`, `classification`, `output`, `error`,
`exit_code`, `duration_ms`, `executed`, `blocked`.

**Gate order (enforced in sequence):**
1. **Scope gate** — checked BEFORE classification; unknown server → `denied`; invalid scope → `denied`.
2. **Classification gate** — tool must be classified as `read` to proceed.
3. Arg schema validation (if schema has `arg_schemas`).
4. Server config check (enabled, non-empty command).
5. Command policy.
6. Network policy.
7. Input size limit.

**Invariants:**
- Scope gate always runs before classification.
- Unknown server (not in `.sac/mcp.toml`) defaults to scope `denied` and is blocked before classification.
- Server-supplied `"classification"` fields in transport responses are **ignored**; only local static classification applies.
- `output` is always redacted via `redact_secrets()` before returning.
- `error` text never contains caller-supplied `input_data` content.
- `blocked=True` when a gate prevents execution; `executed=True` when subprocess or stdio actually ran.
- `SAFECODE_MCP_STDIO_RUNNER=0` (default): uses subprocess shim path.
- `SAFECODE_MCP_STDIO_RUNNER=1`: routes through `StdioReadOnlyAdapter` when server has `argv`.

**Scope vocabulary:** `denied` | `read_only` | `write_proposal_required`.
Default for known server without `scope`: `read_only`.
Default for unknown server: `denied`.

**Snapshot:** `tests/snapshots/contracts/mcp_read_contract.json`

---

## Experimental Surfaces

### v5.7.1 Contract Decisions

Two long-deferred promotion decisions were resolved at v5.7.1:

**Decision 1 — Sandbox real-execution: PROMOTE to stable contract.**
`SandboxExecutionProposal` / `SandboxApproval` / `SandboxResultRecord` are
promoted to stable (Section 17). The preflight + env gate combination has
sufficient safety evidence. The no-default-docker invariant ensures no
accidental real execution.

**Decision 2 — OTel exporter and HTML session report: FREEZE experimental.**
Both surfaces remain EXPERIMENTAL and are marked frozen. The OTel event schema
has changed without versioning; a versioned schema is required before v6.0
promotion. The HTML report is generated output, not a stable API contract.

### v4.0 Promotion Decision Pass

The v3.99.1 promotion pass reviewed candidate surfaces for the v4.0 contract
cut. A surface may be stable only when docs, snapshot, tests, and release
history support the claim.

| Candidate | Decision | Rationale | Evidence |
|---|---|---|---|
| CLI `--json` envelope | **promote (already stable)** | The envelope has been documented, snapshot-tested, and stable since v3.7.2. | Section 11; `tests/snapshots/contracts/cli_json_envelope.json`; `TestCLIJSONEnvelopeContract`; v3.7.2 release note |
| MCP read execution | **promote (already stable)** | The read path has explicit scope/classification gates, snapshot coverage, and has remained stable since v3.8.2. | Section 12; `tests/snapshots/contracts/mcp_read_contract.json`; `TestMCPReadContract`; v3.8.2 release note |
| IDE JSON-RPC | **defer** | The VS Code extension has manifest parity tests, but no VSIX build or release-cycle consumption evidence. | `vscode-extension/`; `tests/test_ide_extension_manifest_contract.py`; v3.9.2 release note |
| TUI interactive | **reject stable promotion at v4.0** | The Rich TUI is frozen experimental and has no stable automation-oriented output contract. | Experimental-surface table; `tests/test_tui_interactive_smoke.py`; v3.9.2 release note |
| `sac report html` | **defer** | HTML report rendering is implemented and tested, but not snapshot-promoted as a public contract. | `src/safecode/report/session_html.py`; `tests/test_report_html.py`; v3.6.3 release note |
| Sandbox real-execution opt-in | **defer** | Executor preflight and env gates exist, but backend pass evidence is host-local and insufficient for a stable v4 contract. | `src/safecode/sandbox/executor_preflight.py`; `tests/test_sandbox_executor_preflight.py`; v3.11.2 release note |

No new stable contract is promoted by v3.99.1 itself. The v4.0 cut may preserve
the already-stable CLI JSON envelope and MCP read execution contracts, but it
must not promote IDE JSON-RPC, TUI, HTML report, or sandbox real-execution based
on v3.99.1 evidence.

The following are explicitly experimental. They may change, be removed, or be
promoted to stable contracts in a future release.

| Surface | Why experimental |
|---|---|
| `SafeCodeLocalAPI` beyond `ask()` and `report()` | Not yet snapshot-tested or versioned |
| OpenAI-compatible live provider behavior | Depends on network and API key; not deterministic |
| MCP schema shim | Keyword-based classification fallback; no real JSON-RPC client |
| MCP write execution (`execute_approved_write`, `execute_granted_write`) | Approval gate; result handling subject to change |
| MCP lifecycle (`sac mcp start/stop/restart`) | PID management; not yet stable |
| Subagent payload evolution beyond v2 fields | v2 payload (synthesis + cancellation fields) promoted to supported at v3.4.3; v3+ fields remain experimental |
| TUI (`sac tui interactive`, `sac tui dashboard`) | **Frozen experimental at v3.9.2.** Rich-based; no Textual upgrade. Surface behavior is stable at v3.5.2 baseline but not promoted to a stable contract. Do not rely on output format for automation. |
| IDE bridge (`sac ide ...`, `vscode-extension/`) | VSIX build deferred pending Node/tsc environment; manifest parity enforced by `tests/test_ide_extension_manifest_contract.py`; no marketplace publish in v3.9.x |
| `OtelExporter` (`SAFECODE_OTEL_EXPORTER` env) | **Frozen experimental at v5.7.1.** Event schema has changed without versioning. Disabled by default. Will not be promoted before v6.0 without a versioned schema. |
| `sac report html` | **Frozen experimental at v5.7.1.** Generated HTML output is not a stable API. Will not be promoted before v6.0 without a stable output contract. |

## Contract Test Coverage

All stable contracts are snapshot-tested in `tests/test_public_contract_snapshots.py`.
The tool registry is additionally snapshot-tested in `tests/test_tool_schema_registry.py`.

Run contract snapshot tests:

```bash
PYTHONPATH=src python3 -m pytest tests/test_public_contract_snapshots.py -q
```
