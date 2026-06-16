---
name: Current SafeCode Agent Baseline
description: >
  Current implemented SafeCode Agent baseline. Read this with the shared
  runtime summary before implementing the next version.
---

# Current Baseline - v5.5.2

## Status
Implemented. Git baseline: tag `v5.5.2`. Local working version: `v5.5.2`.
v5.5.2 completes the production train: PyPI + Homebrew distribution, CI release
job, production docs. First production release.

## Stage
The v4.14–v4.18 usability trains are complete (14 versions shipped):

v4.14–v4.16 train (8 versions):
- `v4.14.0`: provider-profile UX
- `v4.14.1`: first-run diagnostic clarity
- `v4.14.2`: `--model` flag parity
- `v4.15.0`: `sac init` front door
- `v4.15.1`: session-scoped model switching
- `v4.15.2`: keychain and env-only credentials
- `v4.16.0`: bare `sac` enters shell
- `v4.16.2`: error-message rewrite + `sac why`

v4.17–v4.18 shell & interaction UX train (6 versions):
- `v4.17.0`: streaming token-by-token output (ask --stream, shell)
- `v4.17.1`: shell interaction polish (readline history, tab completion, /clear, Rich Markdown)
- `v4.17.2`: live connectivity diagnostics (doctor --live, provider status --live)
- `v4.17.3`: Levenshtein fuzzy matching for model/provider names
- `v4.18.0`: diff rendering in shell + per-patch undo (--checkpoint, --list)
- `v4.18.1`: agent-loop transparency (Rich Status spinner, on_step callback)
- `v4.18.2`: safety-regression fix for `--checkpoint <id>` ToolCallGate

v4.19.x local observability polish train (3 versions):
- `v4.19.0`: `sac task stats` — read-only per-task iteration/budget/pinned summary
- `v4.19.1`: `sac memory size` — read-only .sac/ byte/file breakdown by scope
- `v4.19.2`: docs cut — README, MVP guide, troubleshooting, matrix, guards

v4.20.x native tool protocol train (3 versions):
- `v4.20.0`: NativeToolSpec/Call/Result, NativeToolDispatcher, AgentNativeToolCallResponse; B4/B5/B17 fixes
- `v4.20.1`: read_file, list_files, search_files, grep_files — auto-approved, path-validated, redacted
- `v4.20.2`: docs cut — README, MVP guide, troubleshooting, matrix, guards

v4.21.x write-side native tool train (3 versions):
- `v4.21.0`: edit_file/write_file tools (checkpointed, approval-gated); B6/B7/B8 fixes
- `v4.21.1`: run_command tool via ShellRunner/policy stack
- `v4.21.2`: docs cut — README, MVP guide, troubleshooting, matrix, guards

v4.22.x multi-tool turn train (3 versions):
- `v4.22.0`: MultiToolTurnRunner (dispatch_calls/run_turn/identity_sequence); B9 stuck-loop outside task → warning not abort
- `v4.22.1`: B10 /clear resets AgentSessionStore; B11 EOF prints [exiting shell]; sac[N]> prompt; /undo /history /tools
- `v4.22.2`: docs cut — README, MVP guide, troubleshooting, matrix, guards

v4.23.x Anthropic/Claude first-class provider train (3 versions):
- `v4.23.0`: AnthropicLLMClient.choose_tool_native(); _native_spec_to_anthropic(); _extract_native_result(); B2 content validation; B3 StreamTimeoutError 30s; B16 Doctor._live_anthropic_ping()
- `v4.23.1`: OpenAICompatibleLLMClient.choose_tool_native(); _native_spec_to_openai(); B1 choices[] bounds check; B12 _sanitize_retry_reason() URL/secret stripping
- `v4.23.2`: docs cut — README provider table, MVP guide "First-run with Claude", threat model addendum, matrix rows, guards

v4.24.x Web + GitHub integration train (3 versions):
- `v4.24.0`: web_fetch — HTTP GET, text/HTML only, _strip_html(), _MaxRedirectHandler(3), 50KB cap, requires network: true, URL not in errors
- `v4.24.1`: github_read_issue/read_pr/read_file — gh CLI shell=False; _validate_gh_name(); path traversal blocked; base64 decode for read_file
- `v4.24.2`: github_create_pr/github_push_branch — approval-gated; _validate_branch(); force=True explicit; docs cut: README, MVP guide, matrix rows, guards

v4.25.x Reliability Hardening train (3 versions):
- `v4.25.0`: CheckpointIntegrityError; _sha256_of_file(); backup_sha256 stored in create(); _restore_checkpoint() pre-flight sha256 verification; backward compat for sha256=None (B13 fix)
- `v4.25.1`: Doctor._sac_dir_diagnostics() — sac_dir_writable probe + disk_space WARN; _init_live_connectivity_check() — post-setup ping with yellow warning on fail (B14 + B15 fixes)
- `v4.25.2`: docs cut — troubleshooting checkpoint integrity/writable/disk/init-connectivity, matrix rows, guards

v5.0.0 First Stable Contract (1 version):
- `v5.0.0`: 7 tool specs experimental=False; _V5_STABLE_CONTRACTS (12 entries); sac version --json stable_contracts field; public-contracts.md sections 13-16; versioning-policy.md v5.x section; threat model v5.0 note; 26 new tests

All v4 surfaces remain EXPERIMENTAL and carry no stable contract.

## Current Forward Plan
v5.5.x production train complete. All v5.4–v5.5 roadmap goals achieved.
Next: `docs/version-plans/v5.6-to-v5.8-product-roadmap.md` (quality, security, cost guardrails, v6 prep).

v5.4.x train (3 versions):
- `v5.4.0`: MCPNativeToolBridge — MCP read tools as NativeToolSpecs; register_mcp_tools in _build_dispatcher; sac mcp list-native
- `v5.4.1`: MCP write execution — write_proposal_required scope; _handle_mcp_write_proposal; sac mcp execute --grant-id
- `v5.4.2`: MCP docs cut — README, providers.md, mvp-user-guide, troubleshooting; matrix rows

v5.5.x train (3 versions):
- `v5.5.0`: PyPI release CI job — release job in ci.yml triggered on vX.Y.0 tags; needs test; SAFECODE_PUBLISH=1; release preflight + publish --no-dry-run; 11 new CI matrix tests
- `v5.5.1`: Homebrew formula — scripts/update-brew-formula.sh; sac release publish --update-brew; _run_update_brew_formula helper; Formula/safecode-agent.rb template
- `v5.5.2`: Production docs cut — install-update.md install matrix; project-final-status v5.5.2 baseline; README "Production (v5.5)"

Previous: `v4.8.2` final-v4-shell-first-docs-cut — T-4.8.2-A v4.8-final-docs-cut: README adds Python tutorial link and task-first daily loop summary (17-command surface, v4.x train complete, no v5.0 promise); `docs/mvp-user-guide.md` updated to v4.8.x with new Task-First Daily Loop section; `docs/public-contracts.md` adds v4.x series contract summary (zero new stable contracts v4.0–v4.8, all new surfaces EXPERIMENTAL); `docs/versioning-policy.md` adds v4.x train closure section and policy changelog entry; `docs/security/threat-model-v3.6.md` adds v4.x shell-first addendum table (task/profile/resume/commit/memory/debug/smoke surfaces). All existing tests pass; no stable public contract promoted; v4.x train is complete.

Previous: `v4.8.1` v4-tutorials-and-doc-guards — T-4.8.1-A tutorials-v4-rewrite: three tutorials rewritten around the v4.x task-first daily loop (`sac quickstart` → `sac task new` → `sac profile detect` → `sac status` → `sac ask` → `sac edit` or `sac fix --watch` → `sac apply` → `sac commit` → `sac debug last-failure`/`bundle`); all tutorials honest: no auto-apply, no auto-commit, no push, no live provider required, no IDE required; all v4.x surfaces marked EXPERIMENTAL; new `docs/tutorials/python-first-hour.md` (12 sections), `docs/tutorials/typescript-first-hour.md` rewritten, `docs/tutorials/go-first-hour.md` rewritten. T-4.8.1-B docs-claims-guard-extend: new `tests/test_docs_claims_guard.py` with 46 tests verifying tutorial existence, daily-loop coverage, honesty guards (no auto-apply/commit/push/live-provider-requirement), command existence, stack-specific content, failure taxonomy command existence, and visible command documentation coverage. No stable public contract promoted.

Previous: `v4.8.0` smoke-shell-first-and-cli-trim — T-4.8.0-A smoke-shell-first: new `src/safecode/cli_smoke.py` with `sac smoke shell-first` command running 8 deterministic workflow scenarios (docs-edit-task, failing-test-repair-with-fix-watch, command-profile-detection, dirty-tree-refusal, rollback-after-commit-warn, resume-after-sigint, debug-bundle-redaction, pinned-files-in-context) under mock provider only; hidden but callable; JSON output via CLIJSONResponse; 31 tests in `tests/test_smoke_shell_first.py`. T-4.8.0-B cli-surface-trim: root `sac --help` trimmed to exactly 17 visible daily-loop commands (setup, quickstart, status, task, ask, edit, fix, apply, rollback, run, commit, profile, resume, memory, debug, doctor, version); `memory` promoted from hidden to visible; all trimmed commands remain callable; 62 tests in `tests/test_cli_help_surface_v4_8.py`. No stable public contract promoted.

Previous: `v4.7.2` debug-docs — T-4.7.2-A v4.7-docs-cut: README Core Commands documents experimental `sac debug last-failure`, `sac debug bundle`, and `sac audit query`; MVP guide documents the debug workflow (inspect last failure, create bundle, query audit by task/type/date); troubleshooting documents the experimental failure taxonomy with meaning, likely cause, and suggested command for every code category; docs guards verify category docs match the code table and documented commands exist. All v4.7 surfaces remain EXPERIMENTAL; no stable contract promoted.

Previous: `v4.7.1` debug-bundle-and-audit-query — T-4.7.1-A sac-debug-bundle: new experimental `sac debug bundle [--task <id>] [--out <path>] [--force] [--json]` writes a redacted tar.gz containing manifest, version metadata, config snapshot, doctor-equivalent data without shelling through a string, runtime logs, verified audit events, selected task sidecars, project profile, and memory metadata only; it excludes project source code, refuses overwrites without `--force`, and caps output at 5 MiB. T-4.7.1-B sac-audit-query: new experimental read-only `sac audit query [--type <event_type>] [--since <date>] [--task <id>] [--limit N] [--json]` verifies audit integrity before returning deterministic filtered events and never writes audit events. No stable public contract promoted.

Previous: `v4.7.0` failure-taxonomy-and-debug-last-failure — T-4.7.0-A runtime-failure-taxonomy: new experimental runtime-wide `FailureCategory` table covers model output, patch, command, network/provider, sandbox, interruption, loop, budget, dependency, and unknown failures; runtime logs gain an additive optional `failure_category` field while older logs still parse; existing failure paths write redacted category breadcrumbs where doing so does not violate no-I/O classification invariants. T-4.7.0-B sac-debug-last-failure: new experimental `sac debug last-failure [--task <id>] [--json]` reads runtime logs, task sidecars, recent-failure memory, and audit events without executing commands, returning a redacted deterministic category/message/source/task/command/file summary plus the table-derived suggested command. No stable public contract promoted.

Previous: `v4.6.2` memory-docs — T-4.6.2-A v4.6-docs-cut: README Core Commands documents experimental `sac memory show|pin|unpin|add-note|clear`; MVP guide documents unified memory layout, project notes, task notes, pinned files with context quota, and recent failures helping `sac fix`; troubleshooting covers pinned missing files, outside-root pin refusal, memory secret rejection, and stale recent-failure context. Docs guards verify documented v4.6 commands exist. All v4.6 surfaces remain EXPERIMENTAL; no stable contract promoted.

Previous: `v4.6.1` pinned-context-and-fix-memory — T-4.6.1-A pinned-files-in-context: `ContextSelector` reads pinned files from `MemoryFacade`, includes safe pinned files even when they do not match query tokens, caps pinned selections to a bounded quota, preserves keyword-selected files, exposes deterministic `pinned_missing` warnings through selector and collector metadata, and keeps ignore, root-boundary, sensitive-path, and binary-file gates intact. T-4.6.1-B recent-failures-into-fix: `sac fix` and `sac fix --watch` record redacted bounded recent failures to `.sac/memory/recent-failures.jsonl`, keep the newest 200 entries, and include the newest three failures as bounded task context in the prompt to `AgentOrchestrator.edit()`. Existing edit retry-from-last-failure behavior remains available. All v4.6 surfaces remain EXPERIMENTAL; no stable contract promoted.

Previous: `v4.5.1` branch-and-rollback-commit-guard — T-4.5.1-A sac-branch-new: experimental `sac branch new <name> [--json]` validates branch names with local checks plus `git check-ref-format --branch`, refuses existing branches, refuses dirty unrelated changes, creates/switches without force, and never resets. T-4.5.1-B rollback-after-commit-warn: `sac rollback --last` conservatively detects when the latest checkpoint files appear committed, refuses by default with a `git revert <sha>` hint, and supports explicit `--force-uncommit` with an audit event carrying `commit_sha`. Uncommitted rollback behavior is unchanged. All v4.5.1 surfaces are EXPERIMENTAL; no stable contract promoted.

Previous: `v4.5.0` local-commit-and-dirty-tree-guard — T-4.5.0-A sac-commit: new experimental `sac commit [--message-from-task] [--branch <name>] [--include-task-summary] [--json]` stages only files derived from the current task's applied checkpoint/audit metadata and refuses when that file set cannot be determined. Local Git helpers live in `src/safecode/git/local.py` and use argv-only `subprocess.run([...], shell=False)`; no push or remote operations. T-4.5.0-B dirty-tree-guard: `sac apply` and `sac commit` refuse unrelated tracked/staged changes, ignore untracked files outside touched directories, block untracked files inside touched directories, and allow explicit `--allow-unrelated-changes`. All v4.5.0 surfaces are EXPERIMENTAL; no stable contract promoted.

Previous: `v4.4.2` resume-recovery-budget-docs — T-4.4.2-A v4.4-docs-cut: README Core Commands documents experimental `sac resume`, `sac task budget show`, and `sac task budget set`; MVP guide documents resume after Ctrl-C, interrupted task recovery, task budget usage, and stuck-loop guard behavior; troubleshooting documents interrupted tasks, `budget_exceeded`, `loop_stuck`, and resume refusing closed tasks. Docs guard tests cover the new commands. All v4.4 surfaces remain EXPERIMENTAL; no stable contract promoted.

Previous: `v4.4.1` budgets-and-stuck-loop — T-4.4.1-A task-budget-config: new experimental `src/safecode/task/budget.py` stores per-task budget sidecars under `.sac/tasks/budgets/` with defaults steps=8, time_seconds=600, retries=2, tokens=60000; `sac task budget show|set [--task <id>] [--json]` validates positive integers and refuses missing/closed tasks. `AgentLoop.run()` enforces the step budget and records experimental `failure_category: budget_exceeded` with the tripped budget. T-4.4.1-B stuck-loop-guard: `AgentLoop` tracks consecutive identical tool intent identities `(intent.type, intent.target, intent.tool_name, intent.description)`, aborts after 3, journals experimental `failure_category: loop_stuck`, and records a task marker where CURRENT exists. Budget and stuck categories remain experimental; no v4.7 taxonomy work started; policy/approval gates unchanged.

Previous: `v4.4.0` resume-and-interrupt — T-4.4.0-A sac-resume: new experimental top-level `sac resume [<task_id>] [--json]`; selects explicit task, CURRENT, or newest open/interrupted task; refuses closed tasks; sets CURRENT; reopens interrupted tasks to open; prints a redacted passive resume summary (task id, goal, last command, last fix iteration, pending patch state, next safe step) without running fix/edit/apply/run. T-4.4.0-B sigint-durable-interrupt: `sac edit`, `sac fix`, `sac fix --watch`, and `sac run` catch KeyboardInterrupt only, mark the current task interrupted with an append-only iteration marker, record journal/audit interruption metadata where available, print `resume with: sac resume`, and exit 130. Pending patch files are not modified. All v4.4.0 surfaces are EXPERIMENTAL; no stable contract promoted.

Previous: `v4.3.2` fix-watch-docs — T-4.3.2-A v4.3-docs-cut: README Core Commands documents experimental `sac fix --watch`, `--max-iterations`, `--timeout-seconds`, and `--rerun-suite`; MVP guide documents the approval-gated loop `sac fix --watch` → review → `sac apply` → `sac fix --watch`; troubleshooting documents `loop_no_progress`, `command_timeout`, max iterations reached, blocked suite command, and missing profile suite. All v4.3 surfaces are marked EXPERIMENTAL; `sac fix --watch` never auto-applies; no stable contract promoted. Docs guard tests extended.

Previous: `v4.3.1` fix-loop-guards — T-4.3.1-A no-progress-stop: `sac fix --watch` stops before proposing a follow-up patch when the current failing redacted tail hash matches the previous failing fix iteration; task sidecar and JSON use experimental `failure_category: loop_no_progress` and suggest `sac status` / manual inspection. T-4.3.1-B fix-timeout-and-broader-tests: `sac fix --timeout-seconds N` added (default 120); command timeout exits 124, records `failure_category: command_timeout`, and does not propose a patch; `--rerun-suite test|all` added, with `all` running profile suites in deterministic order `test`, `lint`, `typecheck`, `build` through `ShellRunner`/policy, skipping missing suites with JSON notes, and stopping safely on blocked suite commands. Targeted slice green.

Previous: `v4.3.0` fix-watch-mode — T-4.3.0-A fix-loop-iteration-record: `TaskIteration` now carries experimental fix-loop metadata (`mode`, `suite`, `exit_code`, `tail_hash`, `pending_patch_path`, `status`, `created_at`) while preserving existing v4.1 fields; `record_fix_on_task()` stores one append-only record per fix proposal/failure using sha256 of a bounded redacted tail; plain `sac fix` records proposed pending-patch details without changing PatchProposal or AuditEvent. T-4.3.0-B fix-watch-mode: `sac fix --watch [--max-iterations N=3] [--rerun-suite test]`; one invocation runs the selected test command, proposes a pending patch on failure, exits with next step `sac apply` then rerun; after apply, a later watch rerun can mark the task passing/applied. `--watch` never auto-applies. JSON output includes task_id, iteration_index, test_command, test_exit_code, pending_patch_path, next_step. 2 new test files plus extended sac fix tests; targeted slice green.

`v4.2.2` project-tooling-doctor-and-docs — T-4.2.2-A doctor-missing-deps: `Doctor._project_tooling_diagnostics()` in `src/safecode/doctor.py`; no profile → single SKIP "run sac profile detect"; with profile → one diagnostic per kind: PASS (detected+binary present), SKIP (not detected or missing_dependency=True); missing tool → SKIP not FAIL; SKIP includes binary name + "sac profile set <kind>" hint; 4 diagnostics per kind (project_tooling_test/_lint/_typecheck/_build); preserves diagnostic substrate contract. T-4.2.2-B v4.2-docs-cut: README "Profile commands (v4.2, EXPERIMENTAL)" section with detect/show/set/clear/run suite; docs/mvp-user-guide.md updated to v4.2.x + full profile flow section; docs/troubleshooting.md missing-tool guidance; all v4.2 surfaces EXPERIMENTAL. 30 new tests; full suite 4005 passed, 2 skipped; contract snapshots green.

Previous: `v4.2.1` run-suite-and-fix-profile — T-4.2.1-A sac-run-suite: `sac run --suite test|lint|typecheck|build`; reads `.sac/project_profile.json`; missing profile → "run sac profile detect" guidance (exit 1); missing kind → actionable next-step (exit 1); auto-approved (treated as --yes=True); high-risk still blocked via policy; exit codes 125/126 per v2.8.8; audit/task wiring unchanged from sac run. T-4.2.1-B fix-uses-profile: `sac fix` precedence: --test-command > profile test command > ProjectTestDetector; profile never auto-set by `sac fix`. 43 new tests; full suite 3991 passed, 2 skipped; contract snapshots green.

Previous: `v4.2.0` project-profile — T-4.2.0-A project-profile-detector: new `src/safecode/project/profile.py`; `ProjectProfile` Pydantic model (payload_version=1, test/lint/typecheck/build: ProfileCommand|None, user_overrides: frozenset[str]); `ProfileCommand` (command: tuple[str,...], stack, source: detected|user|none, missing_dependency: bool); atomic persist to `.sac/project_profile.json`; detect for Python (pytest/ruff/mypy), Node (npm/pnpm/yarn package.json scripts), Go (go test/vet/build), Rust (cargo test/clippy/check/build); missing tool → missing_dependency=True (command kept visible); user overrides survive detect and always win; detection never executes project commands. T-4.2.0-B sac-profile-cli: new `src/safecode/cli_profile.py`; `sac profile detect|show|set <kind> "<cmd>"|clear <kind>`; `set` parses with shlex.split and rejects ; | & $ ` and newline; `show --json` deterministic; profile_app registered in cli.py; fixed matrix heading from v4.0.1 to v4.1.2. 87 new tests; full suite 3972 passed, 2 skipped; contract snapshots green.

Previous: `v4.1.2` task-history-filter-and-docs — T-4.1.2-A history-task-filter: `sac history --task <id>` (EXPERIMENTAL) filters audit table to events with exact `metadata.task_id` match; `AuditLogger.read_by_task_id(task_id, limit=200)` added (empty id → [], missing file → [], corrupted lines skipped, raw events returned); `AuditEvent` field set unchanged. T-4.1.2-B v4.1-docs-cut: README Core Commands updated with `sac task`, `sac status`, `sac history --task` (all EXPERIMENTAL); `docs/mvp-user-guide.md` version updated to v4.1.x and "Task-First Flow (v4.1, EXPERIMENTAL)" section added. 17 new targeted tests; full suite 3885 passed, 2 skipped; contract snapshots green.

Previous: `v4.1.1` sac-status-and-task-wiring — T-4.1.1-A sac-status-cmd: new `src/safecode/cli_status.py`; `sac status [--json]`; pure `next_step(state, pending_patch_exists)` truth table; TTY/non-TTY deterministic; never writes audit events. T-4.1.1-B wire-edit-apply-rollback-into-task: new `src/safecode/task/wiring.py`; `get_or_create_current_task()` + record helpers; `sac edit|apply|rollback|fix|run` now attach to CURRENT task; task sidecar mutated on each command; `AuditLogger.write()` extended with optional `task_id` keyword stuffed into metadata; AuditEvent field set unchanged. 26 new tests; full suite 3868 passed, 2 skipped.

Previous: `v4.1.0` task-state-sidecar-and-cli — T-4.1.0-A task-state-sidecar: new `src/safecode/task/state.py` (`TaskState` Pydantic model, payload_version=1, status enum open|applied|interrupted|closed, `TaskIteration`, `TaskCommand`) and `src/safecode/task/store.py` (`TaskStore` with atomic writes, `.sac/tasks/<id>.json`, `INDEX`, `CURRENT`; refuses payload_version>1; missing files never crash). T-4.1.0-B task-cli-core: `sac task new|list|show|switch|close|delete` registered in `cli.py`; all support `--json` via `CLIJSONResponse`; `new` requires non-empty goal, sets CURRENT; `delete` requires `--yes`; `show` redacts secrets; `list` deterministic. 58 new tests; full suite 3842 passed, 2 skipped.

Previous: `v4.0.1` post-v4-roadmap-metadata-alignment — documentation and metadata patch only. `README.md`, `.claude/versions.json`, `docs/version_implementation_matrix.md`, `docs/product-commercialization-roadmap.md`, and `uv.lock` now agree that the active forward plan is `docs/version-plans/v4.1-to-v4.8-shell-first-roadmap.md`, with `docs/version-plans/v3.7-to-v4.0-product-roadmap.md` preserved as the previous plan and `docs/commercial-v1-readiness-audit-v3.11.x.md` as the current readiness baseline. No runtime behavior changes and no stable contract changes.

Previous: `v4.0.0` contract-cut — T-4.0.0-A v4-contract-cut: applies the v3.99.1 promotion decisions without runtime feature work. `docs/public-contracts.md` records the v4.0.0 contract cut: no new stable contracts promoted at v4.0.0, zero breaking changes to v3.0 public contracts, CLI JSON envelope and MCP read execution preserved as already-stable v3.x contracts, and IDE JSON-RPC/TUI/HTML report/sandbox real-execution opt-in deferred or rejected as documented. `docs/commercial-v1-readiness-audit-v3.11.x.md` and `docs/versioning-policy.md` agree with the final result.

Previous: `v3.99.1` promotion-decisions — T-3.99.1-A promotion-decision-pass: `docs/public-contracts.md` records v4.0 candidate decisions with evidence. CLI `--json` envelope and MCP read execution are treated as already-stable promotions from v3.7.2/v3.8.2; IDE JSON-RPC, `sac report html`, and sandbox real-execution opt-in are deferred; TUI stable promotion is rejected for v4.0. `tests/test_public_contract_snapshots.py` pins the decision table and verifies deferred surfaces are not stable-contract headings. No runtime features or new stable contracts added in v3.99.1.

Previous: `v3.99.0` v4-readiness-audit — T-3.99.0-A v4-readiness-audit: new `docs/commercial-v1-readiness-audit-v3.11.x.md` re-audits current v3.11.x reality against the v4.0 readiness goals; PyPI distribution, VS Code release evidence, loop-eval blocking, live-provider green train, CI bench evidence, and sandbox real-execution contract promotion are explicitly deferred rather than claimed shipped. T-3.99.0-B versioning-policy-doc: `docs/versioning-policy.md` now states patch never changes public contracts, minor may add experimental surfaces, major is reserved for public contract changes, and the v4.0 churn budget is at most two new stable contracts with zero v3.0 breaking changes; README links the current audit and policy. Targeted/full/preflight validation run in release train.

Previous: `v3.11.2` sandbox-executor-preflight — T-3.11.2-A sandbox-executor-preflight: new `src/safecode/sandbox/executor_preflight.py`; `sac sandbox executor-preflight <backend>` accepts noop/docker/seatbelt/bubblewrap aliases; records passing preflight state; real Docker/Seatbelt/Bubblewrap execution now requires both a passing backend preflight record and explicit env opt-in (`SAFECODE_SANDBOX_DOCKER=1`, `SAFECODE_SANDBOX_SEATBELT=1`, `SAFECODE_SANDBOX_BUBBLEWRAP=1`); approval claim remains after preflight/env gates. T-3.11.2-B sandbox-promotion-docs: docs/install-update.md and threat model document backend promotion state; `sac doctor` reports Noop/promotion state per backend; default recommendation remains Noop. 6 new tests in `tests/test_sandbox_executor_preflight.py`, threat-model docs extended; full suite: 3767 passed, 2 skipped.

Previous: `v3.11.1` policy-diff — T-3.11.1-A policy-diff: `sac config diff --against strict|balanced|experimental` compares effective config to named preset knob-by-knob; deterministic sorted output; `--json` uses `CLIJSONResponse`; diff surface is limited to policy knobs and does not expose provider/base-url or secret-bearing config; preset definitions unchanged; 5 new tests in `tests/test_policy_diff.py`. Full suite: 3759 passed, 2 skipped.

Previous: `v3.11.0` directory-ephemeral-trust — T-3.11.0-A per-directory-trust: user-level `trust.roots` config applies only from trusted user config, may include subdirectories, and project-local trust declarations are ignored/blocked with `trust_config_lookup` audit events; effective trust never bypasses approval, audit, redaction, checkpoint, rollback, or policy strictness; 4 new tests in `tests/test_per_directory_trust.py`. T-3.11.0-B ephemeral-trust: `sac trust grant --until-end-of-session` adds process-local trust only, never writes config/disk grant state, supports revoke, and audits grant/revoke; 4 new tests in `tests/test_ephemeral_trust.py`. Full suite: 3754 passed, 2 skipped.

Previous: `v3.10.2` context-budgets-stack-tutorials — T-3.10.2-A context-budget-docs: new `docs/context-budgets.md`; documents p50 context-pack budget per language preset (baseline-fixture-derived from `tests/snapshots/bench/`); ties to `ContextBudget`/`ContextBudgetPacker`; no unsupported performance claims; 20 new tests in `tests/test_context_budgets_docs.py`. T-3.10.2-B per-stack-tutorial-ts-go: `docs/tutorials/typescript-first-hour.md` and `docs/tutorials/go-first-hour.md` with required sections (`sac quickstart`, `sac ask`, `sac edit`, `sac apply`, `sac rollback`, `sac fix`, safety notes), cross-references, README links; 18 new tests added to `tests/test_landing_docs.py`. Full suite: 3763 passed, 2 skipped.

Previous: `v3.10.1` ci-gates-live-provider — T-3.10.1-A loop-eval-blocking: promotion deferred (no clean CI train recorded); loop-eval remains advisory (`continue-on-error: true`); 4 new tests in `tests/test_eval_loop_mode_ci_gate.py` encoding current truthful state. T-3.10.1-B live-provider-lane-record: v3.10.x release train history recorded in `docs/providers.md`; lane remains advisory; no credential handling changes; 7 new tests in `tests/test_ci_live_lane.py`. Full suite: 3711 passed, 2 skipped.

Previous: `v3.10.0` eval-bench-metrics — T-3.10.0-A `sac eval bench`: new `src/safecode/eval/bench.py`; `EvalBenchRunner` collects wall time, step count, pending-patch hash per fixture; baseline snapshots under `tests/snapshots/bench/`; ±20% tolerance; mocked-clock injectable for deterministic CI; `sac eval --mode bench` and `--update-baseline` CLI; 27 new tests in `tests/test_eval_bench.py`. T-3.10.0-B live-session-metrics: new `src/safecode/metrics/writer.py`; `MetricsWriter` writes JSONL to `.sac/metrics.jsonl`; disabled by default; `SAFECODE_METRICS=1` opt-in; captures step start/end, tool intent, pending patch size (byte count only), retry; 1 MiB size bound; never raises; minimal wiring in `AgentOrchestrator.edit()`; 26 new tests in `tests/test_metrics_writer.py`. Full suite: 3700 passed, 2 skipped.

Previous: `v3.9.3` v3.9.x docs cut — Documentation-only. `README.md` install section updated (local dev, pipx, TestPyPI, offline wheel); Release Flow updated (sync-versions-json step, tag-move pattern, TestPyPI/production publish commands); "IDE and TUI Status" section added. `docs/install-update.md` reflects all v3.9.x additions (signing mechanism, TestPyPI rehearsal, pipx). Version matrix rows v3.9.0–v3.9.3 complete. Claims-vs-implementation table in version note. No runtime changes. Full suite: 3647 passed, 2 skipped.

Previous: `v3.9.2` VS Code extension VSIX + TUI decision — `vscode-extension/` subtree with `package.json`, TypeScript entrypoint (`src/extension.ts`), `tsconfig.json`, `.vscodeignore`; extension spawns `sac api jsonrpc` via stdio; approval prompt is VS Code modal; no telemetry; no marketplace publish. **VSIX build deferred** (tsc absent; manual smoke procedure in version note). `tests/test_ide_extension_manifest_contract.py` (24 tests) enforces parity between `vscode-extension/package.json` and `src/safecode/ide/manifest.py`. TUI decision = **freeze experimental** (Option B; no Textual); `docs/public-contracts.md` updated; `TestTUIFrozenExperimental` (5 tests). Full suite: 3647 passed, 2 skipped.

Previous: `v3.9.1` pipx/brew docs + versioning policy — `docs/versioning-policy.md` (new): patch/minor/major semantics, stable/experimental surfaces, v4.0 churn budget (≤2 new stable contracts; zero breaking v3.0 changes), brew strategy = **defer** (no production PyPI yet). `README.md` links versioning-policy.md. `tests/test_install_docs.py` (18 tests) enforces required install command fragments. `tests/test_versioning_policy_doc.py` (12 tests) enforces policy sections and README link. Full suite: 3617 passed, 2 skipped.

Previous: `v3.9.0` signing truthing + TestPyPI rehearsal — Decision B on signing: `--sign` produces a **detached cosign or gpg signature** (not Sigstore Rekor); `_planned_steps()` labels the mechanism explicitly; `_check_sign_tooling()` error updated; module docstring clarifies. `docs/install-update.md` "Release Signing" section documents the mechanism; "TestPyPI Rehearsal" section documents `--repository test-pypi`. `docs/security/threat-model-v3.6.md` "Release Artifact Integrity" subsection added. `run_release_publish()` gains `repository` param; `_REPOSITORY_URLS` maps `pypi`/`test-pypi`; real uploads via `uv publish --publish-url <url>`; `SAFECODE_PUBLISH=1` required for both. `--repository` CLI option; JSON output includes `repository` field. 6 new tests `TestSigningMechanismDescription` in `tests/test_release_publish_dry_run.py`; 28 new tests in `tests/test_release_publish_repository.py`. Full suite: 3579 passed, 2 skipped.

Previous: `v3.8.2` MCP write-proposal e2e + read contract promotion — `MCPApprovalStore` in `src/safecode/mcp/approval_grant.py`; single-use grants stored outside project root (`SAFECODE_MCP_APPROVAL_DIR`); `execute_granted_write(proposal_id, server, tool, ...)` on `MCPReadOnlyRunner`; consumes grant, routes through stdio, emits `mcp_granted_write_*` audit events, discards pending proposal (single-use); requires `SAFECODE_MCP_STDIO_RUNNER=1` + server `argv`. Section 12 "MCP Read Execution Contract" added to `docs/public-contracts.md`; snapshot at `tests/snapshots/contracts/mcp_read_contract.json`; `TestMCPReadContract` (16 tests); MCP read execution promoted to stable contract; write execution and lifecycle remain experimental. 19 new tests in `tests/test_mcp_write_proposal_e2e.py`. Full suite: 3545 passed, 2 skipped.

Previous: `v3.8.1` MCP per-server scopes + doctor — `MCPServerConfig.scope` field (`denied`/`read_only`/`write_proposal_required`); parsed from `.sac/mcp.toml`; invalid value → `denied` (fail-closed); unknown server → `denied`; known server without explicit scope → `read_only`; scope gate runs BEFORE classification in `call_readonly` and `propose_write`; `read_only` scope blocks write proposals; `write_proposal_required` allows write proposals through existing approval gate. `sac mcp doctor [server]` ([EXPERIMENTAL]) reports binary path, scope, stdio configured, last call status from audit, lifecycle PID; `--json`; pure read. 22 new tests in `tests/test_mcp_per_server_scopes.py`, 23 new tests in `tests/test_mcp_doctor.py`. Full suite: 3510 passed, 2 skipped.

Previous: `v3.8.0` MCP stdio wire + lifecycle — `StdioReadOnlyAdapter` wired into `MCPReadOnlyRunner.call_readonly` behind `SAFECODE_MCP_STDIO_RUNNER=1` env var / `stdio_runner=True` constructor param; classification gate always runs before stdio call; server-supplied classification ignored. `MCPLifecycleManager` (start/stop/restart) added in `src/safecode/mcp/lifecycle.py`; PID files at `.sac/mcp/<server>.pid`; stop() idempotent; each transition emits RuntimeLogger + AuditEvent. `sac mcp start/stop/restart` CLI commands (all [EXPERIMENTAL]). 19 new tests in `tests/test_mcp_stdio_wired.py`, 32 new tests in `tests/test_mcp_lifecycle.py`, 2 tests updated in `tests/test_mcp_stdio_runner.py`. Full suite: 3465 passed, 2 skipped.

Previous: `v3.7.3` v3.7.x docs cut — `README.md` Core Commands updated: `sac setup --wizard`, `sac fix`, `sac fix --test-command`, `--json` usage documented. `docs/mvp-user-guide.md` updated: intro references v3.7.x; quickstart documents stack detection; new "Interactive setup wizard" subsection; new "Fixing failing tests with sac fix" section; new "Machine-readable output" section with stable JSON envelope contract reference. No runtime changes. Full suite: 3414 passed, 2 skipped.

Previous: `v3.7.2` repo recency signal + JSON envelope promotion — `src/safecode/context/selector.py` extended: `ContextSelector._recent_files()` runs `git log -n50 --name-only`, caches by HEAD, adds `_RECENCY_BONUS=2` to keyword-matched files that appear in recent commits; git failures fall back silently; 22 new tests in `tests/test_context_recency.py`. `CLIJSONResponse` promoted to stable contract in `docs/public-contracts.md` Section 11; snapshot at `tests/snapshots/contracts/cli_json_envelope.json`; 12 new tests in `TestCLIJSONEnvelopeContract`; `TestCrossContractDeterminism` extended. Full suite: 3414 passed, 2 skipped.

Previous: `v3.7.1` setup wizard + progress indicator — `sac setup --wizard` added to `src/safecode/cli.py`; non-TTY exits 0 with static template; TTY walks provider/model/policy; switching from mock requires explicit confirm; network requires double-confirm; `_stricter_policy` enforced (wizard cannot lower user-level safety); cancel skips writes; 14 new tests in `tests/test_setup_wizard.py`. `src/safecode/cli_progress.py` (new): `cli_status(msg)` context manager + `StepCounter(n)` class; TTY shows Rich spinner/step counter; non-TTY emits zero extra bytes; 20 new tests in `tests/test_cli_progress.py`. Full suite: 3384 passed, 2 skipped.

Previous: `v3.7.0` sac fix + stack-aware quickstart — `src/safecode/cli_fix.py` (new): `sac fix [--test-command CMD] [--json]`; detects test command via `ProjectTestDetector`, runs it (`shell=False`, 120s timeout), redacts failure output via `redact_secrets()`, invokes `AgentOrchestrator.edit()`, leaves pending patch for `sac apply`; no approval gate bypassed; 22 new tests in `tests/test_sac_fix.py`. `src/safecode/cli_quickstart.py` extended: `_detect_stack()` detects `pyproject.toml` (python), `package.json` (typescript), `go.mod` (go), `Cargo.toml` (rust); `_next_steps_for_stack()` adapts next-step commands; unknown stack unchanged; 11 new tests in `tests/test_quickstart.py`. Full suite: 3360 passed, 2 skipped.

Previous: `v3.6.6` Commercial v1 cut — metadata-only release marker; version bumped to 3.6.6; `.claude/versions.json` updated; version matrix rows for v3.6.4–v3.6.6 added. No runtime changes.

Previous: `v3.6.5` Landing documentation — `docs/why-safecode.md`, `docs/compare.md`, `docs/troubleshooting.md` added; all linked from `README.md`; claims aligned with public contracts; experimental surfaces labeled; 20 new tests in `tests/test_landing_docs.py`.

Previous: `v3.6.4` Threat model documentation — `docs/security/threat-model-v3.6.md` added; covers 9 threat personas; semi-annual review cadence; 14 new tests in `tests/test_threat_model_docs.py`.

Previous: `v3.6.3` Per-session HTML report — `src/safecode/report/session_html.py` (new); `render_session_html(session_id, project_root) -> SessionHtmlReport`; self-contained HTML (no external assets); secrets redacted via `redact_secrets()`; handles missing/invalid sessions gracefully; `sac report html --session <id>` CLI; `sac report` (no subcommand) still renders Markdown; `report_app` Typer group with `invoke_without_command=True`; 30 new tests in `tests/test_report_html.py`. Full suite: 3302 passed, 2 skipped.

Previous: `v3.6.2` OTel exporter — `src/safecode/otel/exporter.py` (new); `OtelExporter.from_env()` reads `SAFECODE_OTEL_EXPORTER` (disabled by default); missing OTel packages → `RuntimeWarning` + disabled; `export_event()` never raises; endpoint never in error text; no telemetry in tests; 36 new tests in `tests/test_otel_exporter.py`.

Previous: `v3.6.1` Release publish + CI matrix — `src/safecode/release/publish.py` (`PublishResult`, `run_release_publish`, `render_publish_result`); `sac release publish --dry-run/--sign`; dry-run deterministic (no subprocess); real publish requires `SAFECODE_PUBLISH=1` + clean matching tag; sign fails closed; CI expanded to Python 3.11/3.12/3.13 × {ubuntu, macos}; advisory `smoke-windows` lane; 38 tests in `tests/test_release_publish_dry_run.py`, 28 tests in `tests/test_ci_matrix.py`.

Previous: `v3.5.2` Interactive TUI — `sac tui interactive` command; `src/safecode/tui/interactive.py`; non-TTY → static snapshot (deterministic, exits 0); TTY → Rich Live display (Ctrl-C exits cleanly); `--refresh` and `--history-limit` options; 24 new tests in `tests/test_tui_interactive_smoke.py`. Full suite: 3148 passed, 2 skipped.

Previous: `v3.5.1` VS Code extension skeleton — `ide/manifest.py` extended with `jsonrpc_transport` (`launch_command=["sac","api","jsonrpc"]`, `protocol="json-rpc-2.0"`, `transport="stdio"`, `contract_version="1"`, `supported_methods`), `pending_diff_targets`, `safecode.apiJsonrpc` command; `_JSONRPC_CONTRACT_VERSION="1"` exported; IDE bridge remains experimental.

Previous: `v3.5.0` LocalAPI JSON-RPC bridge — `src/safecode/api/jsonrpc.py` (new); `src/safecode/api/__init__.py` (new); `src/safecode/cli_api.py` (new); `sac api jsonrpc` CLI (hidden); `process_request` never raises; error text never contains caller params; `CONTRACT_VERSION="1"`; `_SUPPORTED_METHODS=frozenset({"ask","report","edit","apply"})`; writes gated by existing pending-patch safety machinery; 64 new tests in `tests/test_ide_bridge_jsonrpc.py`.

Previous: `v3.4.3` Subagent payload v2 promotion — `CURRENT_PAYLOAD_VERSION=2`; `SUPPORTED_PAYLOAD_VERSIONS={1,2}`; new fields: `synthesis_summary`, `synthesis_key_findings`, `synthesis_risks`, `synthesis_source_task_ids`, `cancelled_task_ids`; old-journal default stays 1; subagent v2 payload promoted to stable contract in `docs/public-contracts.md`. Full suite: 3084 passed, 2 skipped.

Previous: `v3.4.2` Subagent synthesis — `src/safecode/subagents/synthesis.py` (new); `SubagentSynthesisResult` frozen dataclass; `synthesize_findings(findings, llm_client=None, *, max_findings=10)`; parent loop (`_enrich_with_subagent_findings`) calls synthesis before consuming merged findings; output redacted; fallback on LLM failure; `source_task_ids` sorted; 28 new tests in `tests/test_subagent_synthesis.py`.

Previous: `v3.4.1` Subagent cancellation — `CancellationToken` (threading.Event-backed, idempotent) in `pool.py`; `SubagentPool.cancel()` + `run_all(cancellation_token=...)` external token support; cancelled tasks → `blocked=True`, empty `task_id`; no orphan files; completes within 5s in tests; deterministic ordering preserved; 12 new tests in `tests/test_subagent_cancellation.py`.

Previous: `v3.4.0` Subagent pool — `src/safecode/subagents/pool.py` (new); `SubagentPool(project_root, max_workers=2)`; default max 2 (`SAFECODE_SUBAGENT_MAX` env override); invalid env warns + falls back safely; `ThreadPoolExecutor` bounded; results sorted by `task_id`; worker exceptions isolated; 22 new tests in `tests/test_subagent_pool.py`.

Previous: `v3.3.7` Metadata-only full-regression signoff for the v3.3.x MCP stdio series. No runtime changes. Full suite: 3014 passed, 2 skipped. MCP remains experimental.

Previous: `v3.3.6` MCP Stdio Adversarial Hardening — no new features; adds 37 targeted adversarial tests in `tests/test_mcp_stdio_adversarial.py` covering: server-supplied "classification" field in JSON response ignored; CLI `stdio-discover` has no adapter execution path; `--timeout` propagation verified; `StdioReadOnlyAdapter` gates on static classification after merge; shell string in TOML fails at parse time; oversized/malformed server responses fail closed; error text never contains caller-supplied content or server response data; shell metacharacter tool names blocked by classification gate. MCP remains experimental.

Previous: `v3.3.5` Experimental CLI Stdio Inspect/Discover — adds `sac mcp stdio-status` and `sac mcp stdio-discover` commands to `src/safecode/cli_mcp.py`; both clearly labeled EXPERIMENTAL; `stdio-status` reads MCPConfigStore only, no subprocess; `stdio-discover` calls `resolve_stdio_argv` + `discover_stdio_tools`, no tools/call; both support `--json` via `CLIJSONResponse`/`render_json`; fail closed on missing server or missing argv; MCP remains experimental.

Previous: `v3.3.4` Experimental Read-Only Stdio Runner Adapter — adds `StdioReadOnlyAdapter` in `src/safecode/mcp/stdio_runner.py`; disabled by default; not wired into MCPReadOnlyRunner; classification gate blocks write/unknown before any call; all failures return StdioCallResult, never raise; call_args never in error text; RuntimeWarning on block/failure; MCP remains experimental.

Previous: `v3.3.3` Schema Store Merge — adds `merge_discovered_schemas` pure helper in `src/safecode/mcp/schema.py`; static classification always wins; discovered fills description/args when static is absent; no I/O; no subprocess; existing MCPSchemaStore API unchanged; MCP remains experimental.

Previous: `v3.3.2` MCP stdio tools/list Discovery — adds experimental one-shot stdio discovery in `src/safecode/mcp/discovery.py`; `discover_stdio_tools` calls `call_stdio("tools/list")`; fails closed on transport/structural failures; malformed entries skipped; classification always "unknown"; no tools/call; no runner wiring; existing `MCPDiscovery` unchanged; MCP remains experimental.

Previous: `v3.3.1` MCP stdio Config Argv — adds typed stdio server config and argv validation in `src/safecode/mcp/config.py`; `call_stdio` not invoked; existing MCP runner behavior unchanged; MCP remains experimental.

Previous: `v3.3.0` MCP stdio Transport — adds a tightly-bounded stdio JSON-RPC client in `src/safecode/mcp/transport_stdio.py`; tested against local stub servers only; not wired into existing MCP runner; MCP remains experimental.

Previous: v3.2.6 promoted LLM provider layer to documented stable contract; v3.2.5 added advisory live-provider CI lane; v3.2.4 added fan-out config; v3.2.3 added Anthropic; v3.2.2 added structured output validation.

## v4.1.1 (sac-status-and-task-wiring)
`src/safecode/cli_status.py` (new), `src/safecode/task/wiring.py` (new),
`src/safecode/cli_core.py` updated, `src/safecode/cli_fix.py` updated,
`src/safecode/audit/logger.py` updated, `src/safecode/cli.py` updated.
`tests/test_cli_status.py` (new), `tests/test_audit_task_metadata.py` (new).

Key additions:
- `sac status [--json]` (experimental): shows task id/goal/status, pending patch
  presence, last test outcome, last command, next safe step. Never writes audit events.
- Pure function `next_step(state, pending_patch_exists) -> str` with 6-state truth table:
  no task; open+patch; open+failed test; open+no patch; applied; interrupted; closed.
- `src/safecode/task/wiring.py`: `get_or_create_current_task()` (returns CURRENT task
  or auto-creates if none/closed); `record_edit_on_task()`, `record_apply_on_task()`,
  `record_rollback_on_task()`, `record_fix_on_task()`, `record_run_on_task()`.
- `sac edit`: auto-attaches to task; writes `task_edit_wired` audit event with task_id.
- `sac apply`: auto-attaches; records status=applied + checkpoint id; clears patch_id.
- `sac rollback`: auto-attaches; records status=open + checkpoint id.
- `sac fix`: auto-attaches; records test iteration with command/exit_code/tail_sha.
- `sac run`: auto-attaches; updates last_command; writes audit event with task_id.
- `AuditLogger.write(event, *, task_id=None)`: stuffs task_id into metadata["task_id"].
  AuditEvent field set unchanged.
- 26 new tests. Full suite: 3868 passed, 2 skipped.

## v4.1.0 (task-state-sidecar-and-cli)
`src/safecode/task/state.py` (new), `src/safecode/task/store.py` (new),
`src/safecode/cli_task.py` (new), `src/safecode/cli.py` updated.
`tests/test_task_state.py` (new), `tests/test_cli_task.py` (new).

Key additions:
- `TaskState(BaseModel)`: `task_id` (kebab-case ≤39 chars), `goal`, `created_at`,
  `updated_at`, `status` (open|applied|interrupted|closed), `pending_patch_id`,
  `session_id`, `audit_trace_ids`, `iterations (list[TaskIteration])`,
  `last_command (TaskCommand|None)`, `payload_version=1`.
- `TaskIteration(BaseModel)`: `iteration_index`, `event`, `test_command`,
  `test_exit_code`, `failure_tail_sha256`, `pending_patch_id`, `audit_trace_id`.
- `TaskCommand(BaseModel)`: `command`, `exit_code`, `timestamp`.
- `TaskStore(project_root)`: `create(goal)`, `load(task_id)`, `save(state)`,
  `list()`, `current_id()`, `set_current()`, `clear_current()`, `delete()`.
- File layout: `.sac/tasks/<id>.json` (atomic), `.sac/tasks/INDEX`, `.sac/tasks/CURRENT`.
- All writes atomic via `tmp + os.replace`. Refuses payload_version>1 (fail closed).
- Missing files never raise on read paths.
- `sac task new|list|show|switch|close|delete` registered under `task` group.
- All subcommands support `--json` via `CLIJSONResponse` (stable contract 11).
- `new` requires non-empty goal; id = slug+short-hash; sets CURRENT.
- `list` sorted by `created_at` desc; deterministic.
- `show` redacts via `redact_secrets()`.
- `delete` requires `--yes`.
- 58 new tests in `tests/test_task_state.py` + `tests/test_cli_task.py`.
- Full suite: 3842 passed, 2 skipped.

## v3.3.0 (MCP stdio Transport)
`src/safecode/mcp/transport_stdio.py` (new), `tests/test_mcp_transport_stdio.py` (new).

Key additions:
- `call_stdio(argv, method, params, *, call_id, timeout_seconds, max_output_bytes) -> StdioTransportResult`: one-shot stdio JSON-RPC call.
- `StdioTransportResult(frozen dataclass)`: `success`, `result`, `error`, `exit_code`, `stderr`.
- argv list only; `shell=False` always enforced.
- Timeout enforced with process kill; exit code 124 on timeout.
- Max output size enforced; exit code 126 on overflow.
- Fails closed on: malformed JSON, id mismatch, timeout, process exit without output.
- stderr captured and truncated to `_MAX_STDERR_BYTES` (4096); never injected into `error` field.
- Caller-supplied `params` content never copied into error text.
- Never raises; all failure paths return `StdioTransportResult(success=False, ...)`.
- 45 new tests in `tests/test_mcp_transport_stdio.py`.
- No existing MCP runner behavior changed; no MCP contract promoted.

## v3.2.6 (Providers Docs + Provider Contract Promotion)
`docs/providers.md`, `docs/public-contracts.md`, `tests/snapshots/contracts/provider_contract_schema.json`, `tests/test_provider_contract_snapshot.py`, `README.md` added/updated.

Key additions:
- `docs/providers.md`: full reference for supported keys, config, retry, streaming, structured output, cost accounting, fan-out, live CI lane, experimental features.
- `docs/public-contracts.md` section 9: "LLM Provider Contract" with snapshot reference, invariant list, supported provider keys.
- `tests/snapshots/contracts/provider_contract_schema.json`: machine-readable snapshot (sorted keys, no prose, no timestamps).
- `tests/test_provider_contract_snapshot.py`: 66 tests across 10 classes verifying snapshot integrity, top-level fields, config defaults, retry/streaming/structured-output/cost/fanout invariants, experimental features, live CI lane, and live code imports.
- `README.md`: link to `docs/providers.md` added alongside `docs/public-contracts.md`.
- No runtime behavior changes; all v3.2.5 tests pass unmodified.

## v3.2.5 (Live-Provider CI Lane)
`.github/workflows/ci.yml`, `tests/live/`, `tests/test_ci_live_lane.py` updated/added.

Key additions:
- `live-provider` CI job: gated by `vars.ENABLE_LIVE_LLM_TESTS == 'true'`; `continue-on-error: true`; secrets injected as env vars.
- `tests/live/conftest.py`: `pytest_runtest_setup` skips all live tests unless `SAFECODE_LIVE_TESTS=1`.
- `tests/live/test_live_providers.py`: smoke tests for OpenAI + Anthropic with per-test `_require_env()` guard.
- 21 new tests in `tests/test_ci_live_lane.py`: CI structure, gating, no credentials, default path isolation.
- 2 live tests skipped in baseline pytest run.

## v3.2.4 (Provider Fan-out Config)
`src/safecode/config.py`, `src/safecode/llm/factory.py` updated.

Key additions:
- `LLMConfig.fallback_provider: str | None = None`, `fallback_model`, `fallback_base_url`.
- `FanOutLLMClient(primary, fallback=None)`: proxies `ask/plan/choose_tool/propose_patch`; on `RuntimeError` from primary → `_log_fanout` warning + fallback; `PermissionError`/`ValueError` propagate; `RecoverableContractFailure` (value) passes through.
- `_log_fanout(method, exc)`: `RuntimeWarning` with method name + exception type only; no prompt/context content.
- `_create_single_client(config)`: extracted from `create_llm_client` for reuse.
- `create_llm_client` returns `FanOutLLMClient` when `fallback_provider` is set; fallback config has its own fallback fields cleared.
- 24 new tests in `tests/test_llm_provider_fanout.py`.

## v3.2.3 (Anthropic Provider)
`src/safecode/llm/anthropic_client.py` (new), `src/safecode/llm/factory.py` updated.

Key additions:
- `AnthropicLLMClient`: implements `ask`, `plan`, `choose_tool`, `propose_patch`, and `stream_chat`. Uses Anthropic Messages API (`x-api-key`, `anthropic-version` headers; `system` top-level field; `content[].text` extraction; `input_tokens`/`output_tokens` usage).
- `_extract_text(data)`: extracts text from Anthropic content block list.
- `_parse_anthropic_sse(lines)`: handles `content_block_delta`, `message_delta`, `message_stop` SSE event types.
- `_ANTHROPIC_API_VERSION = "2023-06-01"`, `_DEFAULT_MAX_TOKENS = 4096`.
- Factory gains `anthropic` provider key with lazy import.
- Reuses: `retry_call`, `SessionCostAccumulator`, `validate_provider_json`, `parse_sse_stream`, `StreamChunk`.
- Prompt caching: usage metadata recorded when present; `cache_control` headers deferred.
- 30 new tests in `tests/test_llm_anthropic_client.py`.

## v3.2.2 (Structured Output Validation)
`src/safecode/agent/schemas.py`, `src/safecode/llm/openai_client.py` updated.

Key additions:
- `validate_provider_json(raw, *, step, method)`: returns `AgentContractResponse | RecoverableContractFailure`. Soft failures (invalid JSON, missing type, missing required fields, Pydantic validation errors) return `RecoverableContractFailure`. Hard violations (structurally valid wrong type) raise `ValueError`.
- `_REQUIRED_FIELDS_BY_TYPE`: maps each contract response type to its required field set.
- `OpenAICompatibleLLMClient._chat_agent_json` uses `validate_provider_json` instead of `parse_agent_contract_response`.
- `choose_tool()` returns `RecoverableContractFailure` on soft failures (agent loop handles retry).
- `plan()` raises `ValueError` for soft failures (plan failures are not loop-retryable).
- `parse_agent_contract_response` unchanged — existing callers unaffected.
- 38 new tests in `tests/test_llm_structured_output.py`.

## v3.2.1 (LLM Streaming)
`src/safecode/llm/stream.py` (new), `src/safecode/llm/openai_client.py`, `src/safecode/llm/mock.py` updated.

Key additions:
- `StreamChunk(frozen dataclass)`: `delta: str`, `finish_reason: str | None`.
- `StreamResult(frozen dataclass)`: `text: str`, `finish_reason: str | None`.
- `StreamError(RuntimeError)`: raised on non-recoverable stream failures.
- `aggregate_chunks(chunks)`: exhausts Iterator[StreamChunk] into StreamResult.
- `parse_sse_line(line)`: parses one SSE `data:` line; returns None for [DONE]/blanks; raises ValueError for malformed JSON.
- `parse_sse_stream(lines)`: parses SSE line iterator into StreamChunk iterator.
- `SupportsStreaming` Protocol: optional `stream_chat(messages)` capability extension.
- `OpenAICompatibleLLMClient.stream_chat(messages, *, _lines_fn=None)`: real SSE path or injected mock; fails closed on malformed events.
- `MockLLMClient.stream_chat()`: yields one chunk with stable answer text.
- 31 new tests in `tests/test_llm_streaming.py`.

## v3.2.0 (LLM Retry + Cost Accounting)
`src/safecode/llm/retry.py` (new), `src/safecode/llm/cost.py` (new), `src/safecode/llm/openai_client.py`, `src/safecode/doctor.py` updated.

Key additions:
- `retry_call(fn, *, max_attempts=3, base_delay=0.5, get_retry_after=None, log_fn=None)`: retries on URLError and HTTP 429/503; jitter=uniform(0.5,1.5)*base_delay*2^attempt; honors Retry-After header; does not retry 4xx/5xx other than 429/503.
- `TokenUsage` dataclass: prompt_tokens, completion_tokens, total_tokens, cost_usd (always None for now). `__add__` accumulates.
- `SessionCostAccumulator(sac_dir, session_id)`: `record()` atomically accumulates to `.sac/sessions/<id>/cost.json`; `load()` returns None if no file; `total()` returns zero-value if no file.
- `OpenAICompatibleLLMClient.__init__` gains optional `session_id` and `sac_dir`; `_chat()` wraps urlopen in `retry_call`; `_record_usage()` writes cost after successful call.
- `Doctor._last_session_cost_diagnostic()`: PASS with `last_session: prompt=N completion=M total=T` if cost.json found; SKIP otherwise.
- 27 new tests: `tests/test_llm_retry.py` (17) + `tests/test_llm_cost_accounting.py` (10).

## v3.1.1 (Resume + Retry-From-Failure)
`src/safecode/agent/session.py` and `src/safecode/cli_agent.py` updated.

Key additions:
- `AgentSessionStore.load_by_id(session_id)`: returns current session if session_id matches, else None.
- `agent_resume` gains optional `session_id: str = typer.Argument("")`: verifies match, refuses contract_failed status, falls through to existing `resume()`.
- 17 new tests: `tests/test_agent_resume.py` (9) + `tests/test_edit_retry.py` (8).

## v3.1.0 (Autopilot + JSON Output)
`src/safecode/cli_shared_json.py` added. `cli_core.py`, `cli_ops.py`, `cli_agent.py`, `state/journal.py` updated.

Key additions:
- `CLIJSONResponse(BaseModel)`: fields `command`, `status`, `data`, `error|None`. `render_json()` emits sorted-keys indent=2 JSON; null error omitted.
- `--json` on `ask`, `edit`, `apply`, `run`, `doctor`, `version`, `release preflight`, `agent run`.
- `--retry-from-last-failure` on `edit`: reads last failure event from session journal, redacts via `redact_secrets()`, prepends to task context.
- `get_last_failure_context(session_id)` added to `AgentJournalStore`.
- 35 new tests: `tests/test_cli_json_output.py` (25) + `tests/test_agent_autopilot.py` (10).
- All non-JSON output paths byte-compatible with v3.0.0. No safety gate weakened.

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

## Current Forward Plan
The current project status is `docs/project-final-status-and-roadmap.md`.
The active post-v4.14 forward plan is
`docs/version-plans/post-v4.14-usability-roadmap.md`.

Planning stance:
- v4.10-v4.12 resume MVP is complete as of v4.12.3; v4.12.4 only tracks the FastAPI todo project profile.
- DeepSeek, agentic-lite, FastAPI demo, transcript demo, and README front door are implemented.
- v4.14.0 provider-profile UX is implemented and remains EXPERIMENTAL.
- v4.14.1 first-run diagnostic clarity is implemented: top-line verdicts, next-command hints, quickstart honesty.
- Focus next on --model parity, sac init, session-scoped model, keychain credentials, and shell-first usability.
- Keep SafeCode's safety posture: no auto-apply, approval-gated mutation/run/commit paths, checkpoints, rollback, audit, task wiring, and dirty-tree guard.
- Do not promote v4.10-v4.14 surfaces to stable contracts without a separate contract review and evidence pass.

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
