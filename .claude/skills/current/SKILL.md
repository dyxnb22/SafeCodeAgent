---
name: Current SafeCode Agent Baseline
description: >
  Current implemented SafeCode Agent baseline. Read this with the shared
  runtime summary before implementing the next version.
---

# Current Baseline - v3.0.0

## Status
Implemented. Git baseline: tag `v3.0.0`. Local working version: `v3.0.0`.

## Stage
`v3.0.0` Stable Local Safety Runtime — documents and freezes the 8 supported local safety contracts; labels 6 surfaces as explicitly experimental. No new runtime features. All v2.9.9 contract snapshot tests pass.

Previous v2.9.x stage: v2.9.0 expanded loop fixtures; v2.9.1 bounded retry; v2.9.2 deterministic typed trace snapshots; v2.9.3 loop eval CI gate; v2.9.4 MCP static schema classification; v2.9.5 MCP call arg validation; v2.9.6 versioned subagent journal payload (v2.9.7 folded in); v2.9.8 ToolSpec version field and registry snapshot; v2.9.9 public contract snapshot tests.

## v3.0.0 (Public Contract Stabilization)
`docs/public-contracts.md` added. `README.md` updated with link.

Key additions:
- `docs/public-contracts.md`: 8 stable contracts documented with field lists, invariants,
  snapshot references, and CLI workflow descriptions. 6 experimental surfaces explicitly labeled
  (SafeCodeLocalAPI beyond ask/report, live-provider LLM, MCP shim, subagent v2+ payloads, TUI, IDE).
- `README.md` link: "For stable local safety contracts (v3.0), see docs/public-contracts.md."
- No runtime behavior changes; all v2.9.9 snapshot tests pass.

## v2.9.9 (Public Contract Snapshot Tests)
`tests/snapshots/contracts/` (5 new JSON files) and `tests/test_public_contract_snapshots.py` added.

Key additions:
- `config_defaults.json`: SafeCodeConfig field defaults, known policy names, and lowering rules.
- `pending_patch_schema.json`: PatchProposal and PatchBlock field names/types.
- `audit_event_schema.json`: AuditEvent field names, hash-chain invariants, event types from ToolSpec registry.
- `sandbox_schemas.json`: SandboxExecutionProposal/Approval/ResultRecord fields and approval invariants.
- `eval_trace_schema.json`: LoopStepTrace/LoopEvalTrace field names and determinism invariants.
- All snapshots: sorted keys, no prose, no timestamps, no absolute paths.
- Tool registry snapshot (`tests/snapshots/registry/tool_registry_v1.json`) reused from v2.9.8.
- Loop snapshots (`tests/snapshots/loop/*.json`) reused from v2.9.2.
- `TestToolRegistryContract` reuses v2.9.8 snapshot proving cross-version consistency.
- 51 new tests across 7 test classes in `tests/test_public_contract_snapshots.py`.

## v2.9.8 (Tool Spec Registry Versioning)
`src/safecode/tools/registry.py`, `tests/snapshots/registry/tool_registry_v1.json`, and
`tests/test_tool_schema_registry.py` updated.

Key additions:
- `REGISTRY_SCHEMA_VERSION = "1"` module constant; increment when schema field set changes.
- `ToolSpec.version: str = "1.0.0"` — every ToolSpec now exposes a stable version field.
  Default is backward-compatible; all 17 registered tools carry `"1.0.0"`.
- `tests/snapshots/registry/tool_registry_v1.json`: narrow snapshot (name, version,
  permission_category, risk, requires_human_approval, arg name/type/required). No prose.
- `TestToolSpecVersion` (6 tests): all specs have version, semver-like, default stable,
  round-trip, registry schema version exported and numeric.
- `TestRegistrySnapshot` (8 tests): file exists, valid JSON, matches live registry,
  deterministic, sorted keys, tool names sorted, version in all tools, no prose descriptions.
- 14 new tests in `tests/test_tool_schema_registry.py`.

## v2.9.6 (Subagent Journal Payload Versioning + Adversarial Tests)
`src/safecode/subagents/payload.py` (new), `src/safecode/subagents/journal_adapter.py`, and `src/safecode/state/journal.py` updated.

Key additions:
- `SubagentDispatchPayload(BaseModel)`: `payload_version: int = 1` (default), all existing fields (`task_id`, `summary`, `observations`, `files_inspected`, `errors`, `blocked`, `success`), `extra="ignore"`. `SUPPORTED_PAYLOAD_VERSIONS = frozenset({1})`.
- `_event_to_finding` in `journal_adapter.py` uses `SubagentDispatchPayload.model_validate` for typed, tolerant loading. Emits `RuntimeWarning` (not a crash) for parse failures or unsupported future versions.
- `AgentJournalStore.record_subagent_dispatch` always includes `"payload_version": 1` via `setdefault` — does not override caller-provided value.
- Old journals (no `payload_version`) parse via Pydantic default — full backward compat.
- Adversarial tests (v2.9.7 folded in): duplicate task IDs, conflicting observations, near-secret content redaction, malformed payloads, blocked-task merge exclusion, max-cap enforcement, mixed-event lists.
- 30 new tests in `tests/test_subagent_journal_payload_versioning.py`.

## v2.9.5 (MCP Call Schema Arg Validation)
`src/safecode/mcp/schema.py` and `src/safecode/mcp/runner.py` updated.

Key additions:
- `MCPSchemaArg(frozen dataclass)`: `name`, `type_name` (default `"string"`), `required` (default `False`). Provides typed metadata for one tool argument.
- `MCPToolSchema.arg_schemas: tuple[MCPSchemaArg, ...]` — new optional field (default empty). Distinct from legacy `args: tuple[str, ...]`.
- `validate_call_args(tool_schema, call_args) -> str | None`: returns error message when required args are missing or extra undeclared args are present; returns `None` when `arg_schemas` is empty (no-op for schema-less workloads).
- `MCPReadOnlyRunner.call_readonly` validates args after classification, before server config lookup. Invalid calls are logged via `RuntimeLogger` and returned as a blocked result.
- Schema-less workloads (no `arg_schemas`) are completely unaffected.
- 29 new tests in `tests/test_mcp_call_schema_arg_validation.py`.

## v2.9.4 (MCP Tools-List Schema Shim)
`src/safecode/mcp/schema.py`, `src/safecode/mcp/runner.py`, and `src/safecode/mcp/loop_executor.py` updated.

Key additions:
- `MCPSchemaStore.tools_list(server="") -> list[MCPToolSchema]`: returns schemas for a server or all servers. No I/O.
- `MCPSchemaStore.classify_all(server="") -> dict[str, str]`: returns tool→classification mapping.
- `MCPReadOnlyRunner` gains optional `schemas: list[MCPToolSchema]` parameter. `call_readonly` and `propose_write` use `classify_with_schema` instead of `classify_mcp_tool` directly.
- `MCPReadToolExecutor` gains optional `schemas: list[MCPToolSchema]` parameter. `execute` uses `classify_with_schema` for the read-only gate check.
- Schema-absent workloads are unchanged (`classify_with_schema` falls back to keyword matching).
- Declared write tools are blocked in read-only runner even without write-like names.
- Unknown bucket shrinks when schema metadata is present.
- No real JSON-RPC client; no I/O in classification path.
- 24 new tests in `tests/test_mcp_tools_list_schema_shim.py`.

## v2.9.3 (Eval Loop Mode CI Gate)
`.github/workflows/ci.yml`, `pyproject.toml`, and `tests/test_eval_loop_mode_ci_gate.py` updated.

Key additions:
- New `loop-eval` job in CI: runs `sac eval --mode loop` on every push/PR.
- `continue-on-error: true` — advisory initially (will be made blocking after one clean cycle).
- No live provider credentials or network calls required by the job.
- `pyyaml>=6.0.0` added to dev dependencies so test_eval_loop_mode_ci_gate.py can parse the workflow.
- 13 new tests in `tests/test_eval_loop_mode_ci_gate.py`: job presence, advisory flag, no credentials, CLI output checks.

## v2.9.2 (Eval Replay Baseline Snapshot)
`src/safecode/eval/loop_runner.py`, `tests/snapshots/loop/` (6 JSON files), and `tests/test_eval_replay_baseline_snapshot.py` updated.

Key additions:
- `LoopStepTrace(frozen dataclass)`: `step_index`, `tool_intent_type`, `tool_intent_target`, `is_stop_for_user`, `is_first_fail_recoverable`. No prose, no timestamps, no absolute paths.
- `LoopEvalTrace(frozen dataclass)`: `fixture_name`, `steps: tuple[LoopStepTrace, ...]`, `expected_pending_patch`, `patch_hash` (SHA-256 of `expected_patch_contains` fragments). `as_dict()` is JSON-serializable and byte-stable.
- `build_loop_eval_trace(fixture)`: derives a deterministic trace from the fixture definition alone — no runtime LLM calls needed.
- 6 snapshot files in `tests/snapshots/loop/` (one per fixture): `docs-edit.json`, `python-function-fix.json`, `config-update-fix.json`, `test-assertion-fix.json`, `shell-readonly-check.json`, `import-cleanup.json`.
- 30 new tests in `tests/test_eval_replay_baseline_snapshot.py`: type tests, determinism checks, and parametrized snapshot comparisons.

## v2.9.1 (Agent Loop Error Recovery)
`src/safecode/agent/schemas.py`, `src/safecode/agent/loop.py`, `src/safecode/state/journal.py`, and `tests/test_agent_loop_error_recovery.py` updated.

Key additions:
- `RecoverableContractFailure(frozen dataclass)` moved to `agent/schemas.py`: `step`, `method`, `message`. Distinct from `LLMContractViolation` (which is always fail-closed).
- `AgentLoop.step()` detects `RecoverableContractFailure`, journals a `loop_retry` event, and calls `choose_tool()` once more. If the retry also returns `RecoverableContractFailure`, records a permanent failure and returns without further retry.
- Rules observed: retry only for explicitly-recoverable contract failures; never retry user-stop, policy blocks, validation failures, or hard `LLMContractViolation`.
- `JournalEventType` gains `"loop_retry"`; `AgentJournalStore.record_loop_retry()` appends a structured event with `step`, `method`, `message`, and `retry_attempt=1`.
- `ScriptedStep.first_fail_recoverable: bool` (from v2.9.0) now fully wired: `ScriptedLLMClient` returns `RecoverableContractFailure` on first call, then the real tool choice on retry, without advancing `_step_index` early.
- Old journals without `"loop_retry"` events still parse correctly.
- 18 new tests in `tests/test_agent_loop_error_recovery.py`.

## v2.9.0 (Agent Loop Fixture Expansion)
`src/safecode/eval/loop_runner.py` and `tests/test_agent_loop_fixture_expansion.py` updated.

Key additions:
- Six realistic scripted fixtures in `default_loop_fixtures()` (was two): `docs-edit`, `python-function-fix`, `config-update-fix`, `test-assertion-fix`, `shell-readonly-check`, `import-cleanup`.
- `LoopFailureCategory(str, Enum)`: `contract_violation`, `patch_missing`, `patch_content_mismatch`, `loop_error`, `unknown`.
- `ClassifiedLoopFailure(frozen dataclass)`: `category`, `reason`, `as_dict()`.
- `_classify_loop_result()` populates `LoopEvalResult.classified_failures` for every failing result.
- `RecoverableContractFailure(frozen dataclass)` added as a value type for bounded retry (v2.9.1).
- `ScriptedStep.first_fail_recoverable: bool = False` — backward-compatible field.
- `ScriptedLLMClient` tracks `_pending_retry` to deliver the real tool choice after a recoverable failure.
- 31 new tests in `tests/test_agent_loop_fixture_expansion.py`.

## v2.8.10 (Final v2.8 Baseline Sync)
Metadata-only release marker after the v2.8.6/v2.8.7 cleanup landed on top of v2.8.8/v2.8.9.

Key additions:
- Package/runtime version synchronized to `2.8.10`.
- `.claude/versions.json` current tag and local version synchronized to `v2.8.10`.
- `uv.lock` project version synchronized to `2.8.10`.
- No runtime behavior changes.

## v2.8.7 (Subagent Finding Redaction at Journal Boundary)
`src/safecode/subagents/journal_adapter.py` and `src/safecode/agent/loop.py` updated.
`tests/test_subagent_redaction.py` extended with 10 new tests.

Key additions:
- Producer-side redaction in `_event_to_finding()`: `summary`, `observations`, and `errors` are passed through `redact_secrets()` before `SubagentFinding` is constructed.
- `files_inspected` is not redacted (file paths are metadata, not secret content).
- Merge remains idempotent under already-clean input.
- Consumer-side redaction in `AgentLoop._enrich_with_subagent_findings()` remains as defense in depth.
- Agent loop now emits a `RuntimeWarning` if consumer-side redaction still changes merged text (indicates a producer-side gap).
- `sync_versions_json` sorts `merged_tags` by semver so `latest_tags[-1]` always equals the newest tag.
- 10 new tests: `TestJournalBoundaryRedaction` (8 cases) and `TestConsumerSideRedactionWarning` (2 cases).

## v2.8.6 (CLI Sandbox Module Split)
`src/safecode/cli_sandbox.py` rewritten as thin registry.
`src/safecode/cli_sandbox_status.py`, `src/safecode/cli_sandbox_proposal.py`, `src/safecode/cli_sandbox_executions.py` added.

Key additions:
- `cli_sandbox_status.py` (242 LOC): `sandbox_status`, `sandbox_plan`
- `cli_sandbox_proposal.py` (267 LOC): `sandbox_propose`, `sandbox_pending`, `sandbox_discard`, `sandbox_execute`, `sandbox_approve`, `sandbox_approvals`, `sandbox_revoke`, `sandbox_preflight`
- `cli_sandbox_executions.py` (239 LOC): `executions_app` sub-Typer (callback, stats, prune), `sandbox_last_execution`, `sandbox_execution_show`
- `cli_sandbox.py` (42 LOC): thin registry that imports and registers all commands
- No command renamed, no argument reordered, no safety gate weakened.
- Existing 434 sandbox tests pass after updating 2 mock patch targets to the correct sub-modules.

## v2.8.9 (Audit and Hook Event Dedup)
`src/safecode/hooks/runner.py` updated.

Key additions:
- `skipped_by_policy` flag tracks when `allow_medium_after_apply=False`.
- When a hook is skipped by policy, `hook_approval_required` and `hook_completed` are NOT emitted.
- `hook_skipped_by_policy` remains the sole event for policy-disabled hooks.
- `hook_approval_required` only fires when policy allows hooks but approval is missing.
- Audit chain verification backward-compatible — old logs without `hook_skipped_by_policy` still verify.
- 13 new tests in `tests/test_audit_hook_event_dedup.py`.

## v2.8.8 (Shell Exit Code Honesty)
`src/safecode/cli_core.py` and `docs/install-update.md` updated.

Key additions:
- `sac run` exits with `125` for approval-required and `126` for policy-blocked commands.
- `SAFECODE_RUN_LEGACY_EXIT_CODE=1` opt-out: non-executed commands exit with `1` instead.
- Legacy opt-out documented in `docs/install-update.md` with migration guidance.
- 13 new tests in `tests/test_shell_exit_code_honesty.py`.

## v2.8.5 (Release Surface Collapse Full)
`src/safecode/cli_ops.py` and `docs/install-update.md` updated.

Key additions:
- `hidden=True` on `checklist`, `check`, `smoke`, `meta`, `signoff` commands in `release_app`.
- `sac release --help` now shows only `preflight`, `bump`, `changelog`.
- Hidden commands remain callable for backward compatibility.
- `release_signoff()` emits `RuntimeWarning` pointing to `sac release preflight`.
- `docs/install-update.md` notes helpers are hidden from help, signoff deprecated.
- 25 new tests in `tests/test_release_surface_collapse_full.py`.

## v2.8.4 (MCP Shim Schema Prep — experimental)
`src/safecode/mcp/schema.py` added.

Key additions:
- `MCPToolSchema` frozen dataclass: `server`, `tool`, `classification`, optional `description`, `args`.
- `MCPSchemaStore`: in-memory registry with `lookup(tool, server)` and `classify(tool, server)`.
- `classify_with_schema(tool_name, schemas, *, server)`: checks schema first, falls back to `classify_mcp_tool` keyword matching.
- No real JSON-RPC, no I/O, no subprocess calls.
- 30 new tests in `tests/test_mcp_schema_shim.py`.

## v2.8.3 (Agent Loop Typed Actions)
`src/safecode/agent/pending_action.py` added. `src/safecode/agent/loop.py` updated.

Key additions:
- `StopForUserAction`, `PatchPendingAction`, `ToolPendingAction` dataclasses with `to_dict()` for session-state serialization.
- `pending_action_from_dict()` reconstructs typed objects from stored dicts.
- `render_pending_action()` for CLI rendering.
- Loop no longer uses boolean stringification (`"true"`/`"false"`); `requires_approval` and `executable_now` are proper booleans.
- 27 new tests in `tests/test_agent_loop_typed_actions.py`.

## v2.8.2 (Sandbox Backend Strategy Split)
`src/safecode/sandbox/strategy.py` added. `src/safecode/sandbox/planner.py` updated.

Key additions:
- `SandboxBackendStrategy`: pure class with `recommend(capabilities)`, `available_backends(capabilities)`, `describe(backend, capabilities)`. No I/O, no audit, no subprocess.
- `SandboxPlanner` delegates recommendation to `self.strategy`; `_recommend()` method removed.
- 20 new tests in `tests/test_sandbox_backend_strategy.py` proving strategy is independently testable.

## Active Forward Plan
The active plan for v2.8.x, v2.9.x, and v3.0.0 is `docs/version-plans/v2.8-to-v3.0-product-architecture-roadmap.md`.

Planning stance:
- v2.8.x is consolidation and CLI honesty: diagnostic substrate, sandbox split, typed agent actions, MCP schema prep, release surface collapse, sandbox CLI split, subagent redaction at the journal boundary, shell exit-code honesty, and audit/hook event deduplication.
- v2.9.x is deterministic evidence and contract preparation: loop fixture expansion, bounded retry, replay snapshots, CI gate, MCP static schema classification/arg validation, subagent payload versioning, local ToolSpec versioning, and narrowed contract snapshots.
- v3.0.0 is a stable local safety runtime release, not a broad freeze of every experimental API. Freeze documented config, pending patch, audit, sandbox lifecycle, local tool registry, eval trace, and recommended CLI workflow contracts. Keep `SafeCodeLocalAPI` beyond `ask()`/`report()`, live-provider LLM behavior, MCP schema shim, subagent payload evolution, TUI, and IDE surfaces explicitly experimental.
- Prefer the next short user-visible batch: v2.8.5 `release-surface-collapse-full`, v2.8.8 `shell-exit-code-honesty`, then v2.8.9 `audit-and-hook-event-dedup`.

## v2.8.1 (Diagnostic Migration: Doctor + Release + Policy)
`src/safecode/doctor.py`, `src/safecode/release/check.py`, `src/safecode/release/smoke.py`, `src/safecode/release/preflight.py`, `src/safecode/release/signoff.py`, `src/safecode/policy/audit.py` updated.

Key additions:
- `Doctor.run_diagnostics(*, release=False)` returns `list[Diagnostic]`; `Doctor.run()` remains backward-compatible.
- `ReleaseCheckResult.to_diagnostics()`, `SmokeTestResult.to_diagnostics()`, `SmokeTestCase.to_diagnostic()`, `collect_smoke_diagnostics()`, `ReleasePreflightResult.to_diagnostics()`, `ReleaseSignoffResult.to_diagnostics()`, `PolicyAuditResult.to_diagnostics()` expose typed views.
- Unknown git state in release check surfaces as `SKIP`, not `FAIL`.
- 18 new tests in `tests/test_diagnostic_migration.py` covering cross-substrate aggregation, round-trip with legacy shapes, and error propagation.

## v2.8.0 (Diagnostic Core)
`src/safecode/core/__init__.py` and `src/safecode/core/diagnostic.py` added.

Key additions:
- `DiagnosticStatus` enum: `PASS`, `FAIL`, `WARN`, `SKIP` (str-Enum, JSON-friendly).
- `Diagnostic` frozen dataclass: `name`, `status`, `message`, `hints` (tuple[str, ...]), `metadata` (Mapping). `Diagnostic.from_bool()` migrates legacy boolean checks; `as_dict()` and `render_line()` for rendering.
- `DiagnosticGroup` frozen dataclass: `name`, `diagnostics`; exposes `status`, `passed`, `failed_diagnostics`, `warnings`, `skipped`, `render_lines()`, `as_dict()`.
- `aggregate_status()` returns worst severity (PASS < SKIP < WARN < FAIL). `all_passed()` returns True only when every diagnostic is PASS; empty input passes.
- 32 new tests in `tests/test_core_diagnostic.py`.
- Pure substrate: no CLI, file IO, or policy decisions.

## v2.7.9 (Release Surface Collapse Lite)
`src/safecode/release/signoff.py` and `src/safecode/release/checklist.py` updated. `docs/install-update.md` updated.

Key additions:
- `render_release_signoff()` prepends `[deprecated] Use sac release preflight instead.`
- `render_release_checklist()` prepends `[planning helper] ... not a release gate` after heading.
- `docs/install-update.md` main flow adds `sac release sync-versions-json` step.
- 10 new tests in `tests/test_release_surface_collapse.py`.

## v2.7.8 (Versions Governance Preflight)
`src/safecode/release/versions_governance.py` added. `src/safecode/release/preflight.py` updated.

Key additions:
- `check_versions_governance()`: verifies versions.json current_implemented_tag matches latest git tag; verifies SKILL.md has exactly one implemented-baseline entry.
- Integrated into `run_release_preflight` as `versions_governance` field.
- `render_release_preflight` shows `[PASS/FAIL] versions governance`.
- Stale versions.json issues include `sac release sync-versions-json` next-step hint.
- 11 new tests in `tests/test_versions_governance_preflight.py`.

## v2.7.7 (Agent Loop Stub Eval Mode)
`src/safecode/eval/loop_runner.py` added. `src/safecode/agent/loop.py`, `src/safecode/agent/orchestrator.py`, `src/safecode/cli_ops.py` updated.

Key additions:
- `ScriptedLLMClient`: step-indexed scripted sequences, not keyword matching; `LLMContractViolation` on exhaustion.
- Two default fixtures: `docs-edit` and `python-function-fix`.
- `AgentLoop` and `AgentOrchestrator` accept optional `llm_client` injection.
- `sac eval --mode loop` CLI option.
- 13 new tests in `tests/test_agent_loop_eval_mode.py`.

## v2.7.6 (CLI Help Surface Trim)
`src/safecode/cli.py` and `src/safecode/cli_ops.py` updated.

Key additions:
- `queue`, `memory`, `progress`, `rules`, `tui`, `ide`, `export` hidden from `sac --help` (still callable).
- Core new-user commands remain visible in root help.
- 23 new tests in `tests/test_cli_help_surface_trim.py`.

## v2.7.5 (Quickstart Command)
`src/safecode/cli_quickstart.py` added. `src/safecode/cli.py` registers `sac quickstart`.

Key additions:
- `sac quickstart` checks/creates `.sac/config.toml`, displays provider/policy, recommends a demo workflow, prints next-step commands.
- `--demo` materializes the recommended demo project; `--force` overwrites existing config.
- `--yes` skips confirmation (CI-safe). Never claims edit/apply ran.
- README Core Commands updated to include `quickstart`; `docs/mvp-user-guide.md` adds quickstart path.
- 8 new tests in `tests/test_quickstart.py`.

## v2.7.4 (Release Surface Honesty Lite)
`src/safecode/cli_ops.py` and `docs/install-update.md` updated.

Key additions:
- signoff/checklist/check/smoke/meta help text labelled [internal]/[advanced].
- docs main flow clarified: bump→pytest→tag→preflight.
- 18 new CLI surface tests.

## v2.7.3 (Subagent Finding Redaction/Logging)
`src/safecode/agent/loop.py` updated.

Key additions:
- Subagent findings redacted via `redact_secrets()` before context injection.
- Broad except replaced with `RuntimeWarning` log.
- 6 new redaction tests.

## v2.7.2 (Versions JSON Sync)
`sac release sync-versions-json` command added.

## v2.7.1 (Hook Approval Project Binding)
Hook approval directory binding tightened to project scope.

## v2.7.0 (Audit Consolidation Baseline)
Audit event deduplication and consolidation baseline.

## v2.6.21 (v2.6 Final Signoff)
`src/safecode/release/signoff.py` added. `src/safecode/cli_ops.py` exposes `sac release signoff`.

Key additions:
- `sac release signoff` verifies exact tag, release check, and preflight together.
- `docs/version_implementation_matrix.md` now records the completed v2.6.0-v2.6.21 line.
- `tests/test_release_signoff.py` adds focused signoff coverage.

## v2.6.20 (Security Review Documentation)
`docs/security/product-security-review-v2.6.md` added.

Key additions:
- Documents configuration policy, sandbox defaults, hooks, release gates, and trust boundaries.
- Explicitly calls out project-local config not being allowed to lower user-level safety.
- `tests/test_security_review_docs.py` guards required review sections.

## v2.6.19 (Policy Audit Command)
`src/safecode/policy/audit.py` added. `src/safecode/cli_project.py` exposes `sac config policy-audit`.

Key additions:
- Audits canonical/legacy policy names, alias normalization, project config policy, `SAFECODE_POLICY`, and preset safety invariants.
- Reports unknown project/env policies with actionable next steps.
- `tests/test_policy_audit.py` adds helper and CLI coverage.

## v2.6.18 (Doctor Release Diagnostics)
`src/safecode/doctor.py` updated.

Key additions:
- `sac doctor` now reports `release_version`, `release_tag`, `release_docs`, and `release_preflight`.
- Release diagnostics reuse the existing release guard/preflight helpers and remain read-only.
- `tests/test_doctor_release_diagnostics.py` adds focused Doctor and CLI coverage.

## v2.6.17 (CI Workflow Draft)
`.github/workflows/ci.yml` added.

Key additions:
- CI runs full pytest regression on Python 3.11.
- CI runs release smoke, metadata audit, and changelog preview.
- Exact-tag-only gates (`release check`, `release preflight`) remain local release gates.
- `tests/test_ci_workflow.py` verifies the workflow intent.

## v2.6.16 (Release Checklist Upgrade)
`src/safecode/release/checklist.py` updated.

Key additions:
- `sac release checklist VERSION` now reflects the canonical bump, docs, focused/full test, release gate, commit, tag, and exact-tag flow.
- Version inputs are normalized to `vX.Y.Z`.
- `tests/test_release_checklist_upgrade.py` adds renderer and CLI coverage.

## v2.6.15 (Release Changelog Generator)
`src/safecode/release/changelog.py` added. `src/safecode/cli_ops.py` exposes `sac release changelog --from X.Y.Z --to X.Y.Z`.

Key additions:
- Generates Markdown from local `docs/version-notes/vX.Y.Z-*.md` files without writing files.
- Parses first Markdown heading and `## Summary` content for each included release.
- `tests/test_release_changelog.py` adds parser, renderer, and CLI coverage.

## v2.6.14 (Release Command UX Polish)
`src/safecode/release/ux.py` added. Release command renderers now share status labels, next-step formatting, and exit-code semantics.

Key additions:
- `status_label()`, `exit_code()`, `header()`, and `next_steps()` centralize release command output conventions.
- `sac release check/smoke/meta/preflight/bump` outputs now include a common `Status: PASS/FAIL` line.
- `tests/test_release_ux.py` adds focused UX helper coverage.

## v2.6.13 (Release Workflow Documentation)
`README.md`, `docs/install-update.md`, and `src/safecode/release/docs_guard.py` updated.

Key additions:
- README and install/update docs now show the intended bump, test, commit, tag, verify, and preflight sequence.
- Docs explicitly warn that tag version must match `pyproject.toml` and `safecode.__version__`.
- Docs guard recognizes `sac release bump` and `sac release preflight` as release commands.

## v2.6.12 (Version-Note Index Validation)
`src/safecode/release/metadata.py` updated. `sac release meta` and `sac release preflight` inherit stricter metadata validation.

Key additions:
- Version-note files for the current version must have a first Markdown heading that mentions `vX.Y.Z`.
- Duplicate `docs/version-notes/vX.Y.Z-*.md` files are reported as metadata issues.
- `tests/test_release_metadata.py` adds focused heading and duplicate-note coverage.

## v2.6.11 (Release Preflight)
`src/safecode/release/preflight.py` added. `src/safecode/cli_ops.py` exposes `sac release preflight`.

Key additions:
- `run_release_preflight()`: aggregates release check, smoke, metadata, and docs finalization guard.
- `render_release_preflight()`: concise PASS/FAIL summary with focused failure details.
- `ReleaseCheckResult.ok` now includes tag consistency when tag information is available.
- `tests/test_release_preflight.py` adds focused aggregation and CLI tests.

## v2.6.10 (Release Version Bump Helper)
`src/safecode/release/bump.py` added. `src/safecode/cli_ops.py` exposes `sac release bump VERSION [--dry-run]`.

Key additions:
- `bump_versions()`: updates canonical package version files (`pyproject.toml` and `src/safecode/__init__.py`) atomically. Tests validate version shape and runtime consistency instead of carrying patch-release literals.
- Validates `X.Y.Z` format; rejects invalid strings before touching any file.
- Supports `dry_run=True` to preview without writing.
- `tests/test_release_version_bump.py` adds 22 focused tests.

## v2.6.9 (Release Docs Finalization Guard)
`src/safecode/release/docs_guard.py` added. `smoke.py` gains `_check_docs_finalized()` case. `docs/install-update.md` updated with release command section.

Key additions:
- `check_docs_finalized()`: verifies version-note exists, SKILL.md mentions version, README/docs/install-update mentions release commands.
- Integrated into `run_smoke_tests()` as a fast, local, deterministic check.
- `tests/test_release_docs_guard.py` adds focused pass/fail tests.

## v2.6.8 (Release Metadata Index)
`src/safecode/release/metadata.py` added. `src/safecode/cli_ops.py` exposes `sac release meta`.

Key additions:
- `collect_release_metadata()`: collects package version, runtime version, latest git tag, version-notes entries; reports missing note and stale SKILL.md as issues.
- `render_release_metadata()`: human-readable metadata snapshot.
- `tests/test_release_metadata.py` adds 20 tests.

## v2.6.7 (Release Check Next-Step Polish)
`src/safecode/release/check.py` updated with state-aware `_summarise_state()` and improved next-steps.

Key additions:
- Ready state only when version, tree, and tag all confirmed good.
- Tag suggests only what is actually needed; never re-suggests commit/tag when already correct.
- "Tests passed" never appears in output.

## v2.6.6 (Git Tag/Version Consistency Guard)
`src/safecode/release/version_guard.py` extended with `TagConsistencyResult`, `get_exact_git_tag()`, `check_tag_consistency()`.

Key additions:
- `check_tag_consistency()`: tag=None means no tag (not auto-detect); uses `_TAG_AUTO` sentinel for auto-detect.
- `run_release_check()` accepts injected `git_tag` for testability; includes tag result in output.
- `render_release_check()` displays tag consistency row.

## v2.6.5 (Release Smoke-Test Workflow)
`src/safecode/release/smoke.py` added. `src/safecode/cli_ops.py` exposes `sac release smoke`. `tests/test_release_smoke.py` adds 24 tests.

Key additions:
- `run_smoke_tests()` verifies import/version, `sac version`, version consistency, and expected policy-name surface.
- `render_smoke_results()` renders deterministic PASS/FAIL output.
- Smoke checks are fast, local-only, and do not mutate config.

## v2.6.4 (Policy Docs Hardening)
`README.md`, `docs/install-update.md`, and `docs/version-notes/v2.6.4-policy-docs-hardening.md` updated.

Key additions:
- Policy docs now distinguish canonical names (`strict`, `balanced`, `experimental`) from legacy aliases (`normal`, `learning`).
- Docs describe unknown `SAFECODE_POLICY` warning/skip behavior and unknown project-policy merge safety.

## v2.6.3 (Release Checklist Polish)
`src/safecode/release/check.py` added. `src/safecode/cli_ops.py` exposes `sac release check`. `tests/test_release_checklist_polish.py` adds 15 tests.

Key additions:
- `run_release_check()` reports package version, runtime version, version consistency, and working-tree state.
- `render_release_check()` prints human-readable release readiness output and honest next-step hints.

## v2.6.2 (Release Version Consistency Guard)
`src/safecode/release/version_guard.py` added. `src/safecode/release/__init__.py` re-exports the guard. `tests/test_install_update_polish.py` adds version consistency coverage.

Key additions:
- `check_version_consistency()` verifies `pyproject.toml` `[project].version` matches `safecode.__version__`.
- Clear mismatch, missing-file, and malformed-pyproject messages guard against package/runtime drift before tagging.

## v2.6.1 (Migration Hardening)
`src/safecode/config.py`, `src/safecode/setup.py`, `src/safecode/cli.py` updated. `tests/test_migration_hardening.py` adds 39 tests.

Key additions:
- `KNOWN_POLICY_NAMES: frozenset[str]` — all five recognized policy names (`strict`, `balanced`, `experimental`, `normal`, `learning`).
- `is_known_policy_name(name) -> bool` — public helper for callers that need to validate a policy name.
- `_stricter_policy()` hardened: unknown `right`-side name never overrides a known `left`; unknown `left` is compared conservatively as `balanced` (order=1). Prevents unknown project config policies from overriding a user's `experimental` or `balanced` policy.
- `SafeCodeConfig.load()`: unknown `SAFECODE_POLICY` value now issues a `UserWarning` and is ignored; known aliases (`normal`, `learning`) continue to work without warnings.
- `write_setup()` in `setup.py`: accepts all five recognized policy names (`balanced` and `experimental` were previously rejected); error message lists the full valid set.
- `sac setup --policy` help text updated to mention canonical names plus legacy aliases.
- 39 new tests: unknown right/left in `_stricter_policy` via `merge_trusted_config()`, env-var warning/skip behavior, `write_setup()` with all five names, end-to-end legacy alias round-trips, safety knob preservation.
- No new runtime dependencies.

## v2.6.0 (Policy Presets)
`src/safecode/config.py` updated. `tests/test_policy_presets.py` adds 75 tests.

Key additions:
- `POLICY_PRESETS: dict[str, dict]` — maps canonical preset names (`strict`, `balanced`, `experimental`) to their safety-knob dicts. All presets keep `block_high_risk=True`, `restrict_to_project_root=True`, `network_enabled=False`. Allowed command sets are nested: strict ⊆ balanced ⊆ experimental.
- `normalize_policy_name(name) -> str` — resolves `"normal"` → `"balanced"` and `"learning"` → `"experimental"`; unknown names pass through unchanged.
- `apply_policy_preset(config: SafeCodeConfig) -> None` — unconditionally sets `shell.*`, `sandbox.*`, `hooks.*` knobs to the preset values for the canonical policy. No-op for unknown names.
- `POLICY_ORDER` updated with all five names (`strict=2`, `balanced=1`/`normal=1`, `experimental=0`/`learning=0`).
- Backward-compatible: `"normal"` and `"learning"` still load, compare, and merge correctly via `POLICY_ORDER`.
- `SafeCodeConfig.load()` unchanged in v2.6.0; `apply_policy_preset()` is a standalone utility.
- No new runtime dependencies.

## v2.5.4 (Performance Budgets)
`src/safecode/trace/budget.py` added. `src/safecode/trace/__init__.py` updated. `src/safecode/eval/runner.py` updated. `tests/test_performance_budgets.py` adds 40 tests.

Key additions:
- `PerformanceBudget` (frozen dataclass): `context_size_bytes`, `total_command_duration_ms`, `llm_latency_ms` (None = no LLM), `disk_growth_bytes`. All fields default to zero/None.
- `PerformanceBudget.as_dict()`: deterministic, JSON-serializable dict; `total_command_duration_ms` rounded to 3dp.
- `compute_context_size(snapshot)`: total UTF-8 bytes across all file contents in a `{path: content}` snapshot.
- `compute_disk_growth(before, after)`: net bytes added between two snapshots; never negative.
- `ReplayResult.performance_budget: PerformanceBudget | None = None` — backward-compatible new field.
- `TaskReplayRunner._run_in_workspace()` computes and attaches a budget: context from initial snapshot, duration from `time.perf_counter()` across setup+validation commands, disk growth from before/after snapshots. `_error_result()` leaves budget as `None`.
- No new dependencies; stdlib `time` only.

## v2.5.3 (Quality Dashboard Report)
`src/safecode/report/dashboard.py` added. `src/safecode/report/__init__.py` updated. `tests/test_report_dashboard.py` adds 112 tests.

Key additions:
- `ReportSummary` (frozen dataclass): `total`, `passed`, `failed`, `pass_rate` (float [0.0, 1.0]), `category_counts` (`dict[str, int]` keyed by `FailureCategory` value, in enum declaration order; 1.0 pass_rate when total == 0).
- `build_summary(results) -> ReportSummary`: aggregates counts from `result.classified_failures` across all results. Deterministic: categories follow `FailureCategory` enum order.
- `DashboardRenderer.render_markdown(results, title="Eval Report") -> str`: sections — Summary, Failure Categories (omitted when empty), Fixture Results table, Failure Details (omitted when all passing). Pipe characters in Markdown table cells are escaped.
- `DashboardRenderer.render_html(results, title="Eval Report") -> str`: semantically equivalent HTML with `html.escape()` on all user strings; `.pass`/`.fail` CSS classes on status cells; self-contained (no external stylesheet).
- Both renderers are deterministic (byte-identical for same inputs) and snapshot-friendly.
- No new dependencies: uses stdlib `collections.Counter` and `html` only.
- Backward-compatible: `ReplayResult.classified_failures` defaults to `[]` (v2.5.2); no existing fields removed or renamed.

## v2.5.2 (Failure Taxonomy)
`src/safecode/eval/failures.py` added. `ReplayResult` extended with backward-compatible `classified_failures` field. `tests/test_task_eval_failures.py` adds 50 tests.

Key additions:
- `FailureCategory` (`StrEnum`): 11-value taxonomy — `context_miss`, `patch_parse`, `validation`, `command_blocked`, `forbidden_file_write`, `forbidden_file_changed`, `setup`, `timeout`, `model_error`, `audit_unverified`, `unknown`.
- `ClassifiedFailure` (frozen dataclass): `category: FailureCategory`, `reason: str`, `detail: str | None`; `as_dict()` returns a plain JSON-serializable dict.
- `classify_replay_result(result) -> list[ClassifiedFailure]`: deterministic classifier. Returns `[]` for passing results. Prefers structured fields (`forbidden_file_writes_violated`, `forbidden_commands_violated`, `result.error`) over string parsing. Remaining `failure_reasons` matched via known keyword prefixes (not exact strings) using `_categorize_reason()`. Structured reasons are skipped in the string-parsing pass to avoid duplication.
- `_categorize_reason(reason) -> FailureCategory`: internal helper matching on runner-produced prefixes; priority order prevents mis-classification (e.g., "Setup command timed out" → `setup`, not `timeout`).
- `ReplayResult.classified_failures: list[ClassifiedFailure]` — new field with `field(default_factory=list)`, so all existing call sites constructing `ReplayResult` directly continue to work without change.
- `TaskReplayRunner._run_in_workspace()` and `_error_result()` both call `classify_replay_result(result)` and assign to `result.classified_failures` before returning.
- No new dependencies; no existing public fields removed or renamed.

## v2.5.1 (Agent Replay Runner)
`src/safecode/eval/runner.py` extended with `TaskReplayRunner`, `ReplayResult`, `ValidationCommandResult`, and `WorkspaceError`. `tests/test_task_eval_runner.py` adds 68 tests across 18 classes.

Key additions:
- `TaskReplayRunner.run(fixture)`: materialises a workspace, snapshots initial state, runs `repo.setup_commands` (simulated agent actions), snapshots final state, runs `validation_commands`, evaluates all constraints, returns `ReplayResult`.
- `ReplayResult` (dataclass): `fixture_name`, `passed`, `failure_reasons`, `validation_details`, `observed_changed_files`, `workspace_diff`, `network_intent`, `forbidden_commands_violated`, `forbidden_file_writes_violated`, `audit_events_status`, `workspace_path`, `error`.
- `ValidationCommandResult` (frozen dataclass): `command`, `exit_code`, `stdout`, `stderr`, `passed`, `failure_reason`.
- `WorkspaceError(RuntimeError)`: raised for materialisation/setup failures; caught and converted to a failed `ReplayResult`.
- Constraint evaluation: `expected_exit_code` (last command), `expected_output_contains` (combined output), `expected_diff_contains` (workspace unified diff), `expected_files_changed` (on `ExpectedOutcome`), `expected_changed_files` (fixture-level), `forbidden_changed_files` (fixture-level).
- Safety checks: `forbidden_file_writes` matched against observed changed files; `forbidden_commands` matched against validation commands run; `allow_network` represented in `network_intent`; `expect_audit_events` sets `audit_events_status = "pending_no_session_replay_source"` without causing failure (clearly reported, fail-closed design).
- Inline repos: files written from `repo.files` dict; nested paths created. Local repos: `shutil.copytree` to temp dir — source never mutated.
- No new dependencies; uses stdlib `difflib`, `shutil`, `subprocess`, `tempfile`.
- Old `EvalRunner`/`EvalCase`/`EvalResult` preserved verbatim.

## v2.5.0 (Task Eval Fixture Format)
`src/safecode/eval/fixtures.py` and `src/safecode/eval/loader.py` added. `tests/test_task_eval_fixtures.py` covers 71 tests across 10 classes.

Key additions:
- `TaskEvalFixture` (Pydantic `BaseModel`): top-level fixture with `name`, `goal`, `repo`, `expected`, `safety`; optional `description`, `tags`, `timeout_seconds`, `validation_commands`, `expected_changed_files`, `forbidden_changed_files`. `schema_version` field validated against `SUPPORTED_FIXTURE_SCHEMA_VERSIONS = frozenset({1})`.
- `RepoFixture`: `kind="local"` (requires `path`) or `kind="inline"` (uses `files: dict[str, str]`). `setup_commands` for materialisation. Model validator enforces kind/path invariants.
- `ExpectedOutcome`: `kind` in `{"patch", "command", "any"}`. Optional `expected_exit_code`, `expected_output_contains`, `expected_diff_contains`, `expected_files_changed`.
- `SafetyExpectations`: boolean flags (`expect_diff_review`, `expect_checkpoint`, `expect_approval_gate`, `allow_network`) default to conservative values. `forbidden_commands`, `forbidden_file_writes`, `expect_audit_events` are validated-to-be-lists.
- `FixtureLoadError(ValueError)`: raised for all load/validation failures — consistent with project error hierarchy.
- `load_fixture(path)`: checks existence, suffix (`.json` only), reads text, parses JSON, validates dict, calls `_validate()`.
- `load_fixture_from_dict(data)`: validates dict, calls `_validate()`.
- `load_fixtures_from_dir(directory)`: globs `*.json`, collects all errors into one `FixtureLoadError`, returns sorted by fixture name.
- JSON is the canonical format (no new dependencies; consistent with state-file conventions).
- Stable round-trip: `TaskEvalFixture.model_validate_json(fixture.model_dump_json())`.

## v2.4.3 (Cross-Backend Security Evaluations)
`tests/test_sandbox_cross_backend_security_evals.py` added — 82 new tests across 11 classes. One stale comment updated in `test_sandbox_execution_security_evals.py`.

Key additions:
- `TestCrossBackendShellFalse` (6 tests): verifies `shell=False` is passed explicitly for Docker, Seatbelt, and Bubblewrap via recording run functions.
- `TestCrossBackendHashBeforeBinaryCheck` (6 tests): verifies hash mismatch returns before `DockerDaemonChecker.check()`, `shutil.which("sandbox-exec")`, or `shutil.which("bwrap")` is called.
- `TestCrossBackendNetworkDisabledDefault` (7 tests): Docker `--network none`, Seatbelt no `network-outbound` in profile, Bubblewrap `--unshare-net`.
- `TestDockerPrivilegedNeverPresent` (4 tests): `--privileged` must not appear in Docker argv under any option combination.
- `TestCrossBackendEnvNotLeaked` (4 tests): env values not in generated argv, profile text, or `--env` flags — executor always uses `env={}` when rebuilding the request.
- `TestCrossBackendFilesystemBoundary` (6 tests): writable paths outside project root rejected and warned by all three plan builders.
- `TestCrossBackendSensitivePathRejected` (18 tests, parametrized): `.ssh`, `.env`, `.aws`, `credentials`, `token`, `secret` not granted write access in any backend.
- `TestCrossBackendGateApprovalFirst` (9 tests): when `claim_for_execution` returns False, no executor subprocess.run is called; blocked-claim result record written; pending cleared.
- `TestCrossBackendGateResultLifecycle` (12 tests): injected successful and blocked-binary runs write result records with correct `backend` field and clear pending for Docker/Seatbelt/Bubblewrap.
- `TestCrossBackendGateEnvNotInAudit` (6 tests): env values not in audit event messages/metadata or result record JSON for any real backend.
- `TestCrossBackendPreflightRequired` (4 tests): no-approval blocks all three real backends before subprocess; all three write `sandbox_execution_completed` audit event on injected success.
- Fixed stale comment: `test_backend_not_supported_linux_bwrap` previously said `supports_execution=False`; updated to document that as of v2.4.2 the block is via hash mismatch (or `bwrap` not in PATH).

No implementation bugs were found — all three executors already satisfied the cross-backend invariants.

## v2.4.2 (Linux Bubblewrap Real Execution Preview)
`LinuxBubblewrapExecutor` and `BubblewrapExecutionResult` added to `src/safecode/sandbox/bubblewrap.py`. `LinuxBubblewrapAdapter.supports_execution()` now returns `True`. `SandboxExecutionGate.execute_pending()` routes Linux Bubblewrap proposals through `LinuxBubblewrapExecutor` after the atomic approval claim.

Key changes:
- `LinuxBubblewrapExecutor.execute(proposal)` rebuilds the bwrap argv via `BubblewrapArgsBuilder`, verifies `preview_hash` (`sha256(stable_json(argv))`), checks `shutil.which("bwrap")`, then calls `subprocess.run(argv, capture_output=True, shell=False)`. Returns `BubblewrapExecutionResult` (frozen dataclass). Never raises — all failure paths return `executed=False`.
- `SandboxExecutionGate.execute_pending()`: added `"linux_bubblewrap"` routing block before macOS Seatbelt; writes `sandbox_execution_completed` / `sandbox_execution_blocked` audit event; writes result record and clears pending for all paths.
- `LinuxBubblewrapAdapter.build_plan()` warnings and limitations updated to v2.4.2 language.
- `SandboxExecutionPreflight` error message updated: no backend is plan-only now.
- `sac sandbox status` scope panel updated to v2.4.2; Linux Bubblewrap Mode column changed from `plan-only` to `executing (preview)`.
- `sac sandbox plan` backend_mode mapping adds `LINUX_BUBBLEWRAP`; trailing dry-run panel covers all three executing preview backends.
- 34 new tests in `test_bubblewrap_executor.py`. 10 existing tests updated for `supports_execution=True` and v2.4.2 text/version strings.

## v2.4.1 (macOS Seatbelt Real Execution Preview)
`MacOSSeatbeltExecutor` and `SeatbeltExecutionResult` added to `src/safecode/sandbox/seatbelt.py`. `MacOSSeatbeltAdapter.supports_execution()` now returns `True`. `SandboxExecutionGate.execute_pending()` routes macOS Seatbelt proposals through `MacOSSeatbeltExecutor` after the atomic approval claim.

Key changes:
- `MacOSSeatbeltExecutor.execute(proposal)` rebuilds the sandbox profile deterministically via `SeatbeltProfileBuilder`, verifies `preview_hash` (`sha256(profile_text)`), checks `shutil.which("sandbox-exec")`, then calls `subprocess.run(["sandbox-exec", "-p", profile_text, *command], capture_output=True, shell=False)`. Returns `SeatbeltExecutionResult` (frozen dataclass). Never raises — all failure paths return `executed=False`.
- `SandboxExecutionGate.execute_pending()`: added `"macos_seatbelt"` routing block before Docker; writes `sandbox_execution_completed` / `sandbox_execution_blocked` audit event; writes result record and clears pending for all paths.
- `MacOSSeatbeltAdapter.build_plan()` warnings updated to v2.4.1 language.
- `SandboxExecutionPreflight` error message updated: only Linux Bubblewrap was plan-only at v2.4.1 (graduated at v2.4.2).
- `sac sandbox status` scope panel and macOS Seatbelt Mode column updated to v2.4.1.
- `sac sandbox plan` trailing note distinguished Docker and macOS Seatbelt (propose→execute) from Linux Bubblewrap (plan-only at v2.4.1).
- 29 new tests in `test_seatbelt_executor.py`. 14 existing tests updated for `supports_execution=True` and v2.4.1 text/version strings.
- macOS 15+ note: `sandbox-exec` with user profiles causes SIGABRT (exit_code=-6); this is treated as `executed=True` with non-zero exit.

## v2.4.0 (Docker Sandbox Backend Preview)
`DockerExecutor` and `DockerDaemonChecker` added to `src/safecode/sandbox/docker.py`. `DockerSandboxAdapter.supports_execution()` now returns `True`. `SandboxExecutionGate.execute_pending()` routes Docker proposals through `DockerExecutor` after the atomic approval claim.

Key changes:
- `DockerDaemonChecker.check()` runs `docker info` with a 5-second timeout; returns `(available, reason)`. Never raises. Injectable `run_fn` for tests.
- `DockerExecutor.execute(proposal)` rebuilds the docker run argv from stored proposal fields, verifies `preview_hash` integrity, checks daemon availability, then calls `subprocess.run(argv, capture_output=True, shell=False)`. Returns `DockerExecutionResult` (frozen dataclass).
- `SandboxExecutionGate.execute_pending()`: after atomic approval claim, if `proposal.backend == "docker"` delegates to `DockerExecutor`; writes audit event (`sandbox_execution_completed` if ran, `sandbox_execution_blocked` if daemon unavailable/hash mismatch/timeout); writes result record and clears pending for all paths.
- `DockerSandboxAdapter.build_plan()` warnings updated to v2.4.0 language.
- `SandboxExecutionPreflight` error message updated (macOS Seatbelt and Linux Bubblewrap plan-only at v2.4.0; macOS graduated to executing in v2.4.1).
- `sac sandbox status` scope panel and Docker Mode column updated to v2.4.0.
- `sac sandbox plan` trailing note distinguishes Docker (propose→execute flow) from macOS/Linux (plan-only).
- 26 new tests across `test_docker_container_plan.py` and `test_sandbox_execution_gate.py`. 4 existing tests updated for `supports_execution=True` and v2.4 text.

## v2.3.7 (Universal Tool Gate + State Schema Migrations)
`ToolCallGate` added under `src/safecode/tools/gate.py` — the universal pre-flight gate for all write/execute/dispatch CLI paths. `src/safecode/state/migrations.py` added — schema-version migration with fail-closed behaviour for future records.

Key changes:
- `ToolCallGate` wraps `ToolCallAdapter`; exposes `check()` (full arg validation + approval) and `check_intent()` (name + approval only, for CLI entry points where full args aren't yet known). `must_pass()` / `must_pass_intent()` raise `GateError` (a `ValueError` subclass) on failure.
- `GateResult` is a frozen dataclass: `allowed`, `reason`, `validation` (optional).
- `GateError` is a `ValueError` subclass.
- Gate wired into CLI write/execute paths before side effects: `sac edit` (`patch.propose`, `approved=True`), `sac apply` (`patch.apply`, post-confirm), `sac run` (`shell.run`, only when `approved=True`), `sac rollback --last` (`checkpoint.rollback`), `sac sandbox execute` (`sandbox.execute`), `sac mcp call-readonly` (`mcp.call_readonly`), `sac mcp propose-write` (`mcp.propose_write`).
- `schema_version: int = Field(default=1)` added to `AgentSessionState`, `AgentJournalEvent`, and `MCPWriteProposal`.
- `migrate_record(data, record_type)` in `state/migrations.py`: missing field → v1; supported version → normalised; unsupported future version → `SchemaVersionError`.
- Load paths (`AgentSessionStore.load()`, `AgentJournalStore.read()`, `MCPWriteProposalStore.load_pending()`) call `migrate_record()` before model construction. Journal events with unsupported versions are silently skipped; session/proposal with unsupported version returns `None`.
- `CURRENT_SCHEMA_VERSION = 1`, `SUPPORTED_SCHEMA_VERSIONS = frozenset({1})`.
- 65 new tests in `tests/test_tool_call_gate.py` and `tests/test_state_migrations.py`.

## v2.3.6 (Agent Loop Patch Path)
`AgentLoop` now connects to the existing `AgentOrchestrator.edit()` patch proposal workflow.
`sac agent run "goal"` can produce `.sac/pending_patch.json` for a write-class / patch-class
plan item, stop with `stopped_reason == "approval_required"`, and leave target files
unmodified until `sac apply` is run.

Key changes:
- `AgentLoop.step()` routes `patch.propose` intents to `_execute_patch_proposal_step()`.
- `_execute_patch_proposal_step()` delegates to `AgentOrchestrator.edit(goal)` (no duplication
  of patch parsing, validation, diff building, audit logging, or pending patch serialization).
- Fail closed: existing pending patch → stop for approval without overwriting. Proposal
  failure → record error observation, no file modification.
- `MockLLMClient.choose_tool()` returns a patch intent for "calculator" goals (deterministic
  test coverage). `propose_patch()` returns the calculator repair patch for "calculator" tasks.
- `JournalEventType` gains `"patch_proposed"`; `record_patch_proposal()` added.
- `sac agent run` CLI prints a highlighted **Approval Required — Pending Patch** panel.

## Product Review Follow-up (remaining after v2.3.7)
All v2.3.x stabilization items complete. v2.4 real sandbox backend previews can begin:
ordered Docker first, then macOS Seatbelt, then Linux Bubblewrap.

## v2.3.5 (Honest Surface)
CLI output and docs now accurately communicate current enforcement boundaries. `sac sandbox status` opens with an **Execution Scope (v2.3.x)** panel and adds a **Mode** column (`executing` for Noop, `plan-only` for all others). `sac sandbox plan` adds a **Backend Mode** row to the plan table so non-Noop plan-only status is visible before the trailing note. `sac mcp --help` and `mcp tools` output state that MCP is a subprocess JSON shim, not a full JSON-RPC client. `sac subagent --help` and `subagent run-readonly` state that subagents are read-only context/result collectors, not independent LLM investigations. 21 new tests in `tests/test_cli_output_honesty.py` cover all four surfaces.

## v2.3.4 (Onboarding Examples)
`docs/tutorials/` adds guided bug fix, feature edit, docs edit, and safe shell task tutorials. `examples/README.md` points to the built-in workflow commands. `DemoWorkflowSuite` now includes `safe-shell-status`, completing the four onboarding paths alongside existing bug, feature, and docs workflows.

## v2.3.3 (Install/Update Polish)
Package version metadata is synchronized in `pyproject.toml` and `src/safecode/__init__.py`. Root command `sac version` prints the installed SafeCode version and update hint. `sac doctor` now checks `.sac/config.toml`, `.sac/`, and approval directory environment variables in addition to Python, uv, project root, and pyproject.

## v2.3.2 (IDE Bridge MVP)
`src/safecode/ide/bridge.py` adds read-only IDE bridge targets. `sac ide open-diff` materializes the current pending patch diff to `.sac/ide/pending.diff` and prints a file URI/path. `sac ide open-files "query"` prints safe selected project file URIs from the context selector. The IDE manifest includes `safecode.openDiff` and `safecode.openSelectedFiles`.

## v2.3.1 (Config Wizard)
`src/safecode/setup.py` adds `write_setup()` for project setup. Root command `sac setup` writes `.sac/config.toml` for provider/model/network/policy choices and `.sac/setup.env` with external approval directory environment variables. Existing setup files are protected unless `--force` is passed.

## v2.3.0 (Interactive TUI)
`src/safecode/tui/dashboard.py` adds a Rich-rendered dashboard for current agent sessions. `sac tui dashboard` displays session status, plan progress, pending approval/action JSON, pending patch diff preview, and recent journal history in one terminal view. It is read-only and does not mutate session, patch, journal, or audit state.

## v2.2.6 (Subagent Findings Context Integration)
`src/safecode/subagents/journal_adapter.py` adds `findings_from_journal_events(events)` and `merge_journal_subagent_findings(events, max_observations=20, max_files=50)`. The adapter reads `subagent_dispatch` journal events, converts compatible payloads to `SubagentFinding` via `_event_to_finding()` (returns `None` on malformed payload, never raises), and delegates merge to `merge_subagent_findings()`. `AgentLoop.step()` now calls `_enrich_with_subagent_findings(session_id, context)` between context collection and `choose_tool`: when the session journal has prior dispatch events, the merged result is injected as `"subagent_findings"` in the context dict passed to the LLM. Fail closed: any exception leaves context unchanged. Blocked/failed subagents contribute only errors/provenance, not content. No change to execution behavior or subagent dispatch.

## v2.2.5 (Subagent Result Merge Policy)
`src/safecode/subagents/merge_policy.py` adds `SubagentFinding` and `MergedSubagentContext` (both frozen dataclasses) and `merge_subagent_findings(findings, max_observations=20, max_files=50)`. Merge rules: only successful findings contribute to summary/observations/files; deduplication preserves first occurrence; errors and `blocked_task_ids` are collected from failed/blocked findings; empty task IDs are silently skipped; caps applied after dedup; never raises. `AgentLoop` journal payload keys already match `SubagentFinding` fields — no execution behavior changes.

## Source Of Truth
- Version index: `docs/version_implementation_matrix.md`
- Release roadmap: `docs/release_roadmap_v0_1_to_v1_0.md`
- Productization roadmap: `docs/productization-roadmap-to-claude-code.md`
- Active v2.8-v3.0 roadmap: `docs/version-plans/v2.8-to-v3.0-product-architecture-roadmap.md`
- Product review follow-up: `docs/product-review-v2.3.4-followup.md`
- Git baseline: tag `v2.7.9`
- Runtime invariants: `.claude/skills/shared/core-runtime.md`

## Current Capability
SafeCode Agent has a safety-first local runtime centered on controlled file edits, command policy, audit, rollback, and sandbox planning.

The `v2.1.x` stage added repository intelligence on top of the `v2.0.x` MVP:

**v2.1.0 (Code Map):** A repo map builder under `src/safecode/index/` indexes safe files, Python class/function symbols, imports, likely test files with detected test commands, and project script entrypoints (`__main__` guards). `sac index map` outputs a summary or JSON representation. Existing file and symbol indexes remain compatible.

**v2.1.1 (Test/Build Detector):** Extended `src/safecode/project/test_detector.py` to cover pytest, uv pytest, npm/pnpm test/build/lint scripts, Gradle (`./gradlew` preferred), Maven, Go, Cargo, and Python Ruff lint detection. Detection remains proposal-only; execution is still gated by shell policy. `sac test detect` renders policy status without executing; `sac test run` prefers a policy-runnable detected candidate.

**v2.1.2 (Runtime Consolidation):** `src/safecode/cli.py` is now a slim Typer registry; command implementations live in focused `src/safecode/cli_*.py` modules (cli_agent, cli_core, cli_mcp, cli_ops, cli_project, cli_sandbox, cli_shared, cli_subagent, cli_test_demo) — public command names are unchanged. `AgentLoop` now calls `LLMClient.plan()` to create session plans and `LLMClient.choose_tool()` before routing each step through `ToolIntentRouter`. `ContextCollector.collect(query=...)` adds compact repo-map summaries and query-selected context snippets while preserving budget metadata and source lists. Placeholder path and project-detection helpers now fail closed or return a concrete label. Package version and version matrix entries are synchronized to `2.1.2`.

**v2.1.3 (Diff Planner):** `src/safecode/agent/planner.py` adds `DiffPlanner` with `predict(task, context_hint="")` and `compare(plan, proposal)`. `predict()` extracts file-path tokens from task text using a regex (word-boundary + lookbehind `(?<![:/.])` to reject URL fragments); no LLM call. `compare()` produces a `DiffScopeResult` with a `Literal` status: `no_prediction` (vague task), `match`, `within_scope`, or `extra_files`. Duplicate blocks for the same file are deduplicated before comparison. The `patch_proposed` audit event now carries `scope_status` and, when applicable, `scope_warning` in its metadata. `sac edit` prints the warning in yellow after the diff preview. The scope check is advisory only — valid patches are never blocked by it.

**v2.1.4 (Context Debug Command):** `src/safecode/cli_context.py` adds a `context_app` Typer group registered under `sac context`. The `sac context explain "task"` command is read-only and LLM-free: it calls `ContextSelector.select_sources()` to rank and explain file selection, reads budget limits from `SafeCodeConfig`, and calls `RepoMapBuilder.build()` for repository statistics. Output sections: Context Selection (ranked table with score and reason), Budget Metadata (max bytes/tokens), and Repo Map (counts). Sensitive files are excluded via existing `FileIndexer` skip rules. No writes to `.sac/` or any project path.

**v2.2.4 (Subagent Orchestration):** `src/safecode/subagents/executor.py` adds `SubagentRequest` (frozen dataclass: task/scope/max_steps), `SubagentResult` (frozen dataclass: task_id/summary/observations/files_inspected/commands_attempted/blocked_actions/errors/success/blocked), and `SubagentDispatchExecutor`. The executor validates args via `ToolCallAdapter` against the new `subagent.dispatch` spec (required: task str, scope str, max_steps int; `requires_human_approval=False`), enforces max_steps in [1, 10], runs `ReadonlySubagentRunner`, parses result into structured `SubagentResult`, and never raises. `AgentJournalStore` gains `record_subagent_dispatch()` and `"subagent_dispatch"` event type. `ToolIntentRouter` routes `subagent` intents to `subagent.dispatch` (was `subagent.inspect`); `executable_now=True`. `AgentLoop.step()` routes `subagent.dispatch` to `_execute_subagent_dispatch_step()`, which extracts task/scope/max_steps from `intent.description` and `intent.input_json`, calls `SubagentDispatchExecutor`, records the structured result as an observation, and journals a `subagent_dispatch` event with the full payload. Writes confined to `.sac/subagents/` via `FilesystemBoundary`. All failures fail closed.

**v2.2.3 (MCP Approved Write Execution):** `MCPWriteProposalStore` gains `approve_pending(proposal_id)` and `reject_pending(proposal_id)` — both verify ID match and update status. `MCPReadOnlyRunner.execute_approved_write()` runs write tools after proposal approval: enforces server config, command policy, network, input/output size limits; audits with `mcp_approved_write_started/completed`. `MCPApprovedWriteExecutor` (new, in `loop_executor.py`) validates via `ToolCallAdapter`, checks proposal status == "approved", verifies server/tool and proposal_id, calls `execute_approved_write`, discards proposal after execution. Never raises. `AgentLoop.step()` checks for an approved write proposal after `mcp.propose` routing — if found, calls `_execute_mcp_approved_write_step()` which journals an `mcp_call` event with `approved_write=True`. Unapproved/rejected/missing proposals fall through to the existing pending_action path.

**v2.2.2 (MCP Read Tool Loop):** `src/safecode/mcp/loop_executor.py` adds `MCPReadToolExecutor` with `execute(tool_name, input_json)` — validates via `ToolCallAdapter`, classifies tool, calls `MCPReadOnlyRunner`, returns frozen `MCPLoopResult` (observation, success, blocked, exit_code, metadata). Never raises. `ToolIntentRouter._route_mcp()` dynamically classifies tool names: read-only → route `mcp.call_readonly`, `executable_now=True`; write/unknown → route `mcp.propose`, approval required. `AgentLoop.step()` now branches on `executable_now and route == "mcp.call_readonly"` to call `_execute_mcp_readonly_step()`, which runs the executor and records observations. `AgentJournalStore` gains `record_mcp_call()` and `"mcp_call"` event type. Audit via existing `MCPReadOnlyRunner` audit path. Fail closed for all error conditions.

**v2.2.1 (Model Tool Call Adapter):** `src/safecode/tools/adapter.py` adds `ToolCallAdapter` with `validate(tool_name, args)` and `lookup(tool_name)`. `validate()` checks name existence in `ToolRegistry`, required arg presence, and arg types; raises `AdapterError` (a `ValueError` subclass) on any failure. Returns frozen `ToolCallValidationResult` with `tool_name`, `spec`, `resolved_args`, `requires_approval`, `risk`, `permission_category`, and `audit_event`. `ToolIntentRouter` in `src/safecode/agent/tools.py` now calls `ToolCallAdapter.lookup()` for every intent type via a `_REGISTRY_NAMES` mapping; approval is derived from `ToolSpec.requires_human_approval` (authoritative) OR the intent flag. MCP intents default to `mcp.propose_write` (conservative). Unknown registry names fail closed. All public route strings and CLI behavior are unchanged.

**v2.2.0 (Tool Schema Registry):** `src/safecode/tools/registry.py` is rewritten with a complete schema layer. New models: `ToolRiskLevel` (StrEnum: low/medium/high), `PermissionCategory` (StrEnum: read/write/shell/sandbox/mcp/subagent/audit), `ToolArgSchema` (frozen Pydantic: name/type/required/description), `AuditEventRef` (frozen Pydantic: event_type/description), `ToolSpec` (frozen Pydantic: full tool metadata). `ToolRegistry` provides `list()`, `get(name)`, `names()`, `by_permission()`, `by_risk()`, and `requiring_approval()`. 16 internal tools are registered covering the full read/write/shell/sandbox/mcp/subagent/audit surface. Registry is deterministic, keyless, and produces no side effects. `sac tools list` expanded to show Name/Risk/Permission/Approval/Description with `--risk` and `--permission` filters. New `sac tools inspect TOOL_NAME` shows full schema in a rich panel.

## Important Entry Points
- `src/safecode/subagents/journal_adapter.py`
- `src/safecode/cli_sandbox.py`
- `src/safecode/cli_mcp.py`
- `src/safecode/cli_subagent.py`
- `src/safecode/subagents/merge_policy.py`
- `src/safecode/subagents/executor.py`
- `src/safecode/cli.py` — slim Typer registry; imports from cli_*.py modules
- `src/safecode/cli_context.py`
- `src/safecode/tools/adapter.py`
- `src/safecode/tools/registry.py`
- `src/safecode/mcp/loop_executor.py`
- `src/safecode/cli_agent.py`
- `src/safecode/cli_core.py`
- `src/safecode/cli_ops.py`
- `src/safecode/cli_project.py`
- `src/safecode/cli_sandbox.py`
- `src/safecode/cli_subagent.py`
- `src/safecode/cli_test_demo.py`
- `src/safecode/index/repo_map.py`
- `src/safecode/index/files.py`
- `src/safecode/index/python_symbols.py`
- `src/safecode/project/test_detector.py`
- `src/safecode/agent/planner.py`
- `src/safecode/agent/loop.py`
- `src/safecode/agent/approvals.py`
- `src/safecode/agent/schemas.py`
- `src/safecode/agent/session.py`
- `src/safecode/agent/tools.py`
- `src/safecode/context/collector.py`
- `src/safecode/context/selector.py`
- `src/safecode/context/budget.py`
- `src/safecode/state/journal.py`
- `src/safecode/llm/base.py`
- `src/safecode/llm/mock.py`
- `src/safecode/llm/openai_client.py`
- `src/safecode/sandbox/execution.py`
- `src/safecode/sandbox/preflight.py`
- `src/safecode/sandbox/adapter.py`
- `src/safecode/policy/commands.py`
- `src/safecode/shell/`
- `src/safecode/audit/`
- `tests/test_sandbox_execution_security_evals.py`

## Verification
```bash
PYTHONPATH=src python3 -m pytest tests/test_subagent_orchestration.py -q  # v2.2.4 + v2.2.5 + v2.2.6
PYTHONPATH=src python3 -m pytest tests/test_mcp_approved_write.py -q
PYTHONPATH=src python3 -m pytest tests/test_mcp_read_tool_loop.py -q
PYTHONPATH=src python3 -m pytest tests/test_tool_call_adapter.py -q
PYTHONPATH=src python3 -m pytest tests/test_tool_schema_registry.py -q
PYTHONPATH=src python3 -m pytest tests/test_context_explain.py -v
PYTHONPATH=src python3 -m pytest tests/test_repo_map.py -q
PYTHONPATH=src python3 -m pytest tests/test_project_test_detector.py -q
PYTHONPATH=src python3 -m pytest tests/test_diff_planner.py -v
PYTHONPATH=src python3 -m pytest tests/test_agent_session.py tests/test_agent_journal.py tests/test_context_budget.py -q
PYTHONPATH=src python3 -m pytest tests/test_agent_contract.py tests/test_agent_tool_intents.py -q
PYTHONPATH=src python3 -m pytest tests/test_sandbox_execution_security_evals.py -q
PYTHONPATH=src python3 -m pytest -q
uv run sac --help
```

## Compatibility Requirements (v2.2.6 additions)
- `findings_from_journal_events()` and `merge_journal_subagent_findings()` never raise — all malformed payloads are silently skipped.
- `_event_to_finding()` returns `None` (not an exception) for non-dict payloads, missing `"subagent_dispatch"` key, or non-list list fields; the calling loop skips `None` results.
- `AgentLoop._enrich_with_subagent_findings()` catches all exceptions and returns the original context unchanged (fail closed).
- Blocked/failed dispatch events contribute only `errors` and `blocked_task_ids` to context, never `summary`, `observations`, or `files_inspected`.
- `"subagent_findings"` key is only injected when at least one source_task_id, blocked_task_id, or error exists — context for sessions with no prior dispatches is unchanged.
- Subagent execution behavior is unchanged — only context enrichment path added.

## Compatibility Requirements (v2.2.5 additions)
- `SubagentFinding` and `MergedSubagentContext` are frozen dataclasses — callers must not construct mutable copies.
- `merge_subagent_findings()` never raises — all edge cases (empty list, empty fields, all-blocked) return a valid `MergedSubagentContext`.
- Only findings with `success=True` and `blocked=False` contribute to `summary`, `observations`, `files_inspected`, and `source_task_ids`.
- Empty `task_id` strings are silently skipped in both `source_task_ids` and `blocked_task_ids`.
- `max_observations` and `max_files` caps apply after dedup; order is preserved (first N entries).
- `AgentLoop` execution behavior is unchanged — merge_policy is a data-layer module only.
- `SubagentResult` fields map directly to `SubagentFinding` fields; no transformation needed at call sites.

## Compatibility Requirements (v2.2.4 additions)
- `SubagentDispatchExecutor.execute()` never raises — all failures return a blocked `SubagentResult`.
- `max_steps` is validated in [1, 10]; values outside this range return a blocked result without running.
- Subagent writes are confined to `.sac/subagents/{task_id}/` — `FilesystemBoundary` enforces this.
- `commands_attempted` is always empty in `SubagentResult` — subagents execute no shell commands.
- `ToolIntentRouter` route change (`subagent.inspect` → `subagent.dispatch`) is backward-compatible: intents are still `executable_now=True`, no approval required.
- `JournalEventType` `"subagent_dispatch"` is append-only — existing event types are unchanged.
- `AgentLoop._execute_subagent_dispatch_step()` records one `subagent_dispatch` journal event per dispatch.

## Compatibility Requirements (v2.2.3 additions)
- `MCPApprovedWriteExecutor.execute()` never raises — all failures return a blocked `MCPLoopResult`.
- Execution requires proposal status == "approved"; "pending" and "rejected" are always blocked.
- Proposal is discarded after execution regardless of outcome — no replay possible.
- `approve_pending()` only accepts a proposal in "pending" status; already-approved proposals raise `PermissionError`.
- `AgentLoop._find_approved_write_proposal()` performs exact server/tool string match against the stored proposal.
- `mcp_call` journal events for approved writes include `approved_write: True` in the payload.
- Read-only MCP path (`MCPReadToolExecutor`) is unchanged and unaffected by approved-write additions.

## Compatibility Requirements (v2.2.2 additions)
- `MCPReadToolExecutor.execute()` never raises — all failures return a blocked `MCPLoopResult`.
- `MCPLoopResult` is a frozen dataclass — callers must not construct mutable copies.
- `ToolIntentRouter` read-only MCP routing uses `classify_mcp_tool()` keyword matching — same classification logic as `MCPReadOnlyRunner`.
- Only `classify_mcp_tool()` result `"read"` enables `executable_now=True`; write/unknown still require approval.
- MCP write/unknown intents remain backward-compatible: route to `mcp.propose`, approval required.
- `JournalEventType` `"mcp_call"` is append-only — existing event types are unchanged.
- `AgentLoop._execute_mcp_readonly_step()` records one `mcp_call` journal event per execution.
- Audit logging is performed by `MCPReadOnlyRunner` — the executor does not write additional audit events.

## Compatibility Requirements (v2.2.1 additions)
- `ToolCallAdapter.validate()` is validation/adaptation only — it must not execute tools or call the LLM.
- `ToolCallValidationResult` is frozen; callers must not construct mutable copies.
- `AdapterError` is a `ValueError` subclass — callers catching `ValueError` will catch it.
- `ToolIntentRouter` backward compat: all existing route strings and `RoutedToolIntent` fields are unchanged.
- `requires_human_approval` from `ToolSpec` is always respected; registry metadata is authoritative.

## Compatibility Requirements (v2.2.0 additions)
- Tool schema registry is schema/metadata only; no tool execution is performed by the registry layer.
- `ToolSpec`, `ToolArgSchema`, and `AuditEventRef` are frozen Pydantic models — callers must not construct mutable copies.
- High-risk tools must carry `requires_human_approval=True`; WRITE and SHELL permission tools must too.
- `ToolRegistry.get()` raises `KeyError` for unknown names — callers must not swallow this without logging.

## Compatibility Requirements (v2.4.0 additions)
- `DockerExecutor.execute()` never raises — all failure paths return `DockerExecutionResult(executed=False, ...)`.
- `DockerDaemonChecker.check()` never raises — all OS/subprocess errors are caught and returned as `(False, reason)`.
- Preview hash verification is enforced before daemon check; a hash mismatch always blocks execution.
- `shell=False` is mandatory in all `subprocess.run()` calls in `DockerExecutor` and `DockerDaemonChecker`.
- `--privileged` must never appear in the generated docker run argv.
- Network defaults to disabled (`--network none`) unless `proposal.network_enabled=True`.
- The Noop path in `execute_pending()` is unchanged after the Docker branch — no Noop behavior is altered.

## Compatibility Requirements (v2.4.2 additions)
- `LinuxBubblewrapExecutor.execute()` never raises — all failure paths return `BubblewrapExecutionResult(executed=False, ...)`.
- Preview hash verification is enforced before `shutil.which` check and before subprocess; a hash mismatch always blocks execution.
- `shell=False` is mandatory in all `subprocess.run()` calls in `LinuxBubblewrapExecutor`.
- Network defaults to disabled (`--unshare-net` in bwrap argv) unless `proposal.network_enabled=True`.
- Filesystem boundary validation via `BubblewrapArgsBuilder` (sensitive path detection, project root containment, blocked writable roots).
- No env value leakage: `env={}` passed when reconstructing `SandboxExecutionRequest`.
- The Noop, Docker, and macOS Seatbelt paths in `execute_pending()` are unchanged after the Bubblewrap branch.

## Compatibility Requirements
- Keep sandbox execution disabled unless proposal, approval, policy, and preflight checks all allow it.
- Preserve diff review, checkpoint, audit, rollback, command policy, filesystem containment, network deny-by-default, and approval binding.
- Project-local configuration must not weaken user-level safety policy.
- All four backends (Noop, Docker, macOS Seatbelt, Linux Bubblewrap) support execution as of v2.4.2.
- New historical details belong in docs and Git tags, not in additional `.claude/skills/v*` files.
- Real LLM calls must keep network policy and API key requirements explicit; mock mode must remain available for keyless tests.
- Context collection must remain bounded and redacted; budget metadata should explain truncation without exposing hidden content.
- Agent journals must validate session ids and remain summaries rather than hidden context dumps.
- Test detection must not execute commands; `sac test run` must reuse shell policy, approval, and audit gates.
- Repo map and context selection must not bypass redaction or budget limits when incorporating repository intelligence.
- Test/build detection is proposal-only; detected commands must not be executed without going through shell policy and approval gates.
- CLI module split must not change existing public command names or weaken any safety gate.
- Diff planner scope check is advisory only; it must never block or modify a valid patch.
- `DiffScopeResult.status` must remain a constrained `Literal` — callers must not construct results with arbitrary status strings.
