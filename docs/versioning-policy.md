# SafeCode Agent Versioning Policy

## Semantic Versioning Summary

SafeCode Agent uses [Semantic Versioning 2.0.0](https://semver.org/).

| Change type | Version bump | Contract rule |
|---|---|---|
| Patch (Z) | Bug fixes, doc corrections, test additions | Never changes a public contract |
| Minor (Y) | New features, experimental surfaces | May add new experimental surfaces; never removes or breaks stable contracts |
| Major (X) | Breaking contract changes | Required for any change to a v3.0+ stable contract |

## Stable vs Experimental Surfaces

Surfaces documented in `docs/public-contracts.md` as **stable** are governed by
this policy. Surfaces labeled **experimental** may change in any minor release
without notice.

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

- Is required for any breaking change to a v3.0+ stable contract.
- Is required to remove or rename a stable CLI command or option.
- Is required to change a stable contract field name or type.

## v4.0 Contract Churn Budget

The v4.0 contract churn budget is:

- **At most two new stable contracts** promoted from experimental at v4.0.
- **Zero breaking changes** to v3.0 contracts (config precedence, pending patch,
  audit event hash-chain, sandbox approval lifecycle, eval loop trace, CLI JSON
  envelope, LLM provider contract, MCP read execution contract).

Candidates for promotion at v4.0 (to be decided in the v4.0-prep audit):
- IDE JSON-RPC bridge (iff VS Code extension is shipped and stable).
- Sandbox real-execution opt-in (iff executor preflight passes for at least one
  backend).

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

## Policy Changelog

| Version | Change |
|---|---|
| v3.9.1 | Policy document created. Brew decision: defer. |
