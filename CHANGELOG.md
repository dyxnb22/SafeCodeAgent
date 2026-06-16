# Changelog

All notable changes to SafeCode Agent are documented here.

Format: `[vX.Y.Z] — YYYY-MM-DD — short-description`

---

## Unreleased

## [v5.7.0] — 2026-06-16 — threat-model-review-and-subagents

- Completed semi-annual threat model review covering 6 surfaces: trust modes
  (verified existing v5.1.0 documentation), MCP write execution (classification
  gate + scope config + single-use grants), git-aware context (redact_secrets()
  + budget cap + shell=False), parallel subagents (read-only only invariant),
  prompt injection via tool results (structural approval gate cannot be bypassed),
  and native tool path validation (all 8+ tools verified).
- Updated next scheduled review to 2027-06-01.
- Added `dispatch_parallel()` to `MultiToolTurnRunner` using ThreadPoolExecutor
  for concurrent read-only tool calls. Write-classified tools raise ValueError
  at dispatch time. Stable ordering by original index. Error isolation between
  workers.
- New `tests/test_subagent_activation.py` (14 cases): parallel dispatch
  correctness, write tool blocking, performance advantage, error isolation,
  worker crash resilience.
- Extended `tests/test_threat_model_docs.py` (10 new cases): v5.7 review
  section, each surface named, next review date, review log entry.

## [v5.6.2] — 2026-06-16 — golden-demo-project

- Created `examples/golden-demo/` with a deterministic broken calculator fixture
  (subtract returns `a + b` instead of `a - b`) and a passing test after fix.
- Added `examples/golden-demo/demo/run-demo.sh` for mock/no-key playback.
- Added `examples/golden-demo/demo/expected-transcript.md` showing the full
  safety loop: context → diff preview → approval → checkpoint → apply →
  audit → test → commit offer → rollback evidence.
- Added `docs/demo/portfolio-demo.md` explaining the scenario, safety gates,
  and key source files for interviewers.
- README first screen now points to golden-demo as the primary demo.
- New `tests/test_golden_demo.py` (22 cases): verifies fixture is broken,
  fixable, script executable, transcript contains all safety stages, and
  portfolio doc links to source files.

## [v5.6.1] — 2026-06-16 — real-eval-harness

- Added `src/safecode/eval/live.py` with `LiveEvalFixture`, `LiveEvalResult`,
  `LiveEvalRunner`, 5 default live fixtures (python-add-function,
  python-fix-failing-test, python-refactor-rename, go-add-handler,
  ts-fix-type-error), result persistence (`save_latest`, `check_ratchet`),
  and `render_live_summary`.
- Wired `sac eval --mode live` into CLI: skips without `SAFECODE_LIVE_TESTS=1`,
  runs selected or all fixtures, saves to `tests/snapshots/live_eval/latest.json`,
  enforces ratchet (passing fixtures cannot regress below baseline).
- Added `live-eval` CI job (advisory, gated by `ENABLE_LIVE_LLM_TESTS`,
  uploads artifact).
- New `tests/test_live_eval_mode.py` (30 cases, all mock).
- Extended `tests/test_ci_live_lane.py` (7 new cases).

## [v5.6.0] — 2026-06-16 — prompt-engineering-and-hygiene

- Rewrote `SYSTEM_PROMPT` from 5 lines to 8 structured sections covering role,
  tool use strategy, task decomposition, test failure handling, redundant read
  avoidance, stopping conditions, patch format, and safety rules.
- Added `TOOL_USE_PROMPT_SECTION` (injected when native tools are active) and
  `PATCH_FORMAT_PROMPT_SECTION` (injected for legacy patch path).
- Added root portfolio hygiene files: `LICENSE`, `SECURITY.md`,
  `CONTRIBUTING.md`, `CHANGELOG.md`.
- Updated README first screen to be portfolio-ready; demoted Homebrew to
  "coming soon" rather than a required production install channel.
- New `tests/test_system_prompt.py` (13 cases) and `tests/test_project_docs.py`.

## [v5.5.2] — 2025-11-XX — production-docs-cut

- Production docs cut: install matrix, project final status, README "Production (v5.5)".

## [v5.5.1] — 2025-11-XX — homebrew-formula

- Homebrew formula scaffold: `Formula/safecode-agent.rb`, update-brew script,
  `sac release publish --update-brew`.

## [v5.5.0] — 2025-11-XX — pypi-release-ci

- PyPI release CI: `release` job in `ci.yml` triggered on `vX.Y.0` tags.

## [v5.4.2] — 2025-10-XX — mcp-docs-cut

- MCP docs: README, providers.md, mvp-user-guide, troubleshooting, matrix.

## [v5.4.1] — 2025-10-XX — mcp-write-execution

- MCP write execution: `write_proposal_required` scope, `_handle_mcp_write_proposal`,
  `sac mcp execute --grant-id`.

## [v5.4.0] — 2025-10-XX — mcp-native-tool-bridge

- `MCPNativeToolBridge`: MCP read tools as `NativeToolSpec`s; `register_mcp_tools`
  in `_build_dispatcher`; `sac mcp list-native`.

## [v5.3.2] — 2025-09-XX — context-intelligence-docs

- Context intelligence docs and v5.3 complete product baseline.

## [v5.3.1] — 2025-09-XX — context-compaction

- Auto-compress long sessions at 60% threshold.

## [v5.3.0] — 2025-09-XX — context-intelligence

- Git-aware context + import-graph seeding.

## [v5.0.0] — 2025-07-XX — first-stable-contract

- 7 tool specs promoted to `experimental=False`; 12 stable contracts; `sac version --json`.

---

For earlier versions see `docs/version-notes/` and `docs/version_implementation_matrix.md`.
