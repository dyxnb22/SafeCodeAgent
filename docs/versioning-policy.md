# SafeCode Agent Versioning Policy

## Semantic Versioning Summary

SafeCode Agent uses [Semantic Versioning 2.0.0](https://semver.org/).

| Change type | Version bump | Contract rule |
|---|---|---|
| Patch (Z) | Bug fixes, doc corrections, test additions | Patch never changes public contracts |
| Minor (Y) | New features, experimental surfaces | Minor may add experimental surfaces; never removes or breaks stable contracts |
| Major (X) | Breaking contract changes | Major is reserved for public contract changes |

## Stable vs Experimental Surfaces

Surfaces documented in `docs/public-contracts.md` as **stable** are public
contracts governed by this policy. Surfaces labeled **experimental** may change
in any minor release without notice.

## Patch releases

A patch release:

- Fixes bugs without changing public API or contract schemas.
- May add or fix tests.
- May correct documentation that misrepresents the implementation.
- May not add new CLI options, new stable contracts, or new config fields.

## Minor releases

A minor release:

- May add new commands, options, or config fields.
- May add new experimental surfaces (labeled EXPERIMENTAL in docs and output).
- May promote an experimental surface to stable (with a new snapshot test).
- May never remove or rename a stable CLI command, a stable contract field, or
  a stable snapshot.

## Major releases

A major release (e.g., v4.0.0):

- Is reserved for public contract changes.
- Is required for any breaking change to a v3.0+ stable contract.
- Is required to remove or rename a stable CLI command or option.
- Is required to change a stable contract field name or type.

## v4.0 Contract Churn Budget

The v4.0 contract churn budget is:

- **At most two new stable contracts** promoted from experimental at v4.0.
- **Zero breaking changes** to v3.0 public contracts (config precedence,
  pending patch format, audit event hash-chain, sandbox approval lifecycle,
  local tool registry shape, eval loop trace, recommended CLI workflows, and
  hidden/internal release command policy).
- Later stable contracts promoted during v3.x (LLM provider contract, subagent
  payload v2, CLI JSON envelope, and MCP read execution) also remain unchanged
  unless an explicit major-version contract change is documented.

Candidates for promotion at v4.0 (to be decided in the v4.0-prep audit):
- IDE JSON-RPC bridge (iff a shipped VS Code extension has consumed it for a
  release cycle and the surface has docs, snapshot, and tests).
- Sandbox real-execution opt-in (iff executor preflight evidence is strong
  enough for a stable contract and the default remains Noop).

Surfaces that will **not** be promoted at v4.0 without a new evidence pass:
- TUI (`sac tui interactive`) — frozen experimental.
- HTML session report (`sac report html`) — frozen experimental.
- Subagent payload v2+ fields — still versioned-payload experimental.

## Brew Distribution Strategy

**Decision: Defer** (`C`).

Rationale: A Homebrew tap or formula submission requires a stable PyPI release
with consistent artifact hashes. At v3.9.x, the first TestPyPI rehearsal has
been run but no production PyPI wheel has shipped. A tap will be set up once
the first production release is confirmed (target: v3.10.x or v4.0, whichever
lands first with a passing live-provider CI train).

Until then, the supported install paths are:

- **Source checkout** (primary dev path): `git clone` + `uv sync`
- **pipx from TestPyPI** (rehearsal): see `docs/install-update.md`
- **pipx from PyPI** (once available): `pipx install safecode-agent`
- **Offline wheel**: `uv build` locally + `pipx install dist/<wheel>`

## v4.x Train Closure

The v4.x shell-first train (v4.1–v4.8) is now complete as of v4.8.2. The train
added zero new stable contracts. All new v4.1–v4.8 surfaces remain experimental.
The twelve v4.0.0 stable contracts remain stable and unchanged through v4.8.2.

No v5.0 release is currently scheduled. Future contract promotions and major
version decisions will be documented here when they are planned.

## v4.9.x AI Shell Train

The v4.9.x AI shell train (v4.9.0–v4.9.3) is complete as of v4.9.3. The train
added zero new stable contracts. All new v4.9 surfaces (`sac shell`, overview,
router, session state, `sac smoke ai-shell`) are EXPERIMENTAL.

The twelve v4.0.0 stable contracts remain stable and unchanged through v4.9.3.
No deferred surface (IDE JSON-RPC, TUI, HTML report, sandbox real-execution) was
promoted in v4.9. v4.9 does not schedule v5.

## v5.x Contract Promise

v5.0.0 promotes four new stable contracts (sections 13–16 of
`docs/public-contracts.md`):

1. **Native tool schemas** for `read_file`, `list_files`, `search_files`,
   `grep_files`, `edit_file`, `write_file`, `run_command`.
2. **Audit event types** `tool_call_read`, `tool_call_write`, `tool_call_command`.
3. **Write-tool checkpoint rollback** round-trip (write → checkpoint → rollback).
4. **`sac shell` loop** with `/clear`, `/undo`, `/history`, `/tools` and the
   `sac[N]>` prompt format.

The v5.0.0 contract churn budget:
- **Four new stable contracts** promoted from experimental (listed above).
- **Zero breaking changes** to the twelve v4.0.0 stable contracts.
- `web_fetch`, GitHub tools, and provider client internals remain EXPERIMENTAL.
- Any CLI subcommand outside the 17-command visible surface remains EXPERIMENTAL.

For v5.1.x and beyond, the same policy applies: minor releases may add
experimental surfaces; major releases required for any breaking change to any
of the sixteen stable contracts (sections 1–16).

## Policy Changelog

| Version | Change |
|---|---|
| v3.9.1 | Policy document created. Brew decision: defer. |
| v3.99.0 | Policy wording clarified for patch/minor/major semantics and v4.0 churn budget. |
| v4.0.0 | Contract cut honored the budget: zero new v4 stable contracts and zero v3.0 breaking changes. |
| v4.8.2 | v4.x shell-first train closed. Zero new stable contracts added in v4.1–v4.8. No v5.0 currently scheduled. |
| v4.9.3 | v4.9 AI shell train closed. Zero new stable contracts added in v4.9.0–v4.9.3. No v5.0 scheduled. |
| v5.0.0 | First major bump since v4.0.0. Four new stable contracts (native tool schemas, audit event types, write-tool rollback, sac shell loop). Zero v4.x breaking changes. |
| **v5.7.1** | **Sandbox execution promoted to stable (Section 17). OTel/HTML report frozen experimental. Zero breaking changes to earlier stable contracts.** |
