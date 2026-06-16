# Changelog

All notable changes to SafeCode Agent are documented here.

Format: `[vX.Y.Z] — YYYY-MM-DD — short-description`

---

## Unreleased

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
