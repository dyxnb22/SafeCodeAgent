# Commercial v1 Readiness Audit — v3.6.6

Status: planning only. No runtime change in this audit.
Baseline: tag `v3.6.6`, package version `3.6.6`, branch `main`.
Authoring date: 2026-06-03.

This document audits the actual state of SafeCode Agent at v3.6.6 against
the "Definition Of Done For Commercial Product" in
`docs/product-commercialization-roadmap.md` (Section 8). The audit is
brutally honest: a passing local test suite is treated as evidence of
*regression containment*, not of *public release readiness*. Claims that
have no direct evidence in the repository are labeled `not shipped`,
`docs-only`, or `experimental`, regardless of how the prior train
described them.

Sources read for this audit:

- `docs/product-commercialization-roadmap.md`
- `docs/public-contracts.md`
- `docs/why-safecode.md`, `docs/compare.md`, `docs/troubleshooting.md`
- `docs/providers.md`, `docs/security/threat-model-v3.6.md`
- `docs/version_implementation_matrix.md`
- `.claude/skills/current/SKILL.md`
- `.claude/versions.json`
- `README.md`, `pyproject.toml`, `.github/workflows/ci.yml`
- spot checks in `src/safecode/release/publish.py`,
  `src/safecode/otel/exporter.py`, `src/safecode/api/jsonrpc.py`,
  `src/safecode/tui/interactive.py`, `src/safecode/sandbox/{docker,seatbelt,bubblewrap}.py`
- spot check in `tests/live/`

Classification key:

- **shipped** — landed in code, tested, behavior verified.
- **partially shipped** — landed in code, but a documented requirement is unmet.
- **experimental** — landed behind an experimental label, not promoted to a stable contract.
- **scaffolded** — CLI command, code path, or doc exists, but the end-to-end claim is unverified.
- **docs-only** — described in documentation; no runtime or release process actually exercises it.
- **not shipped** — planned in the roadmap, no corresponding work in the repo.
- **deferred** — intentionally postponed; not a gap for v1.

---

## 1. Executive verdict

v3.6.6 is best described as **commercial v1 documentation cut**, not
commercial v1 ship readiness.

Strengths that are real:

- Local safety substrate is solid and snapshot-tested. The eight v3.0
  public contracts hold; provider and subagent v2 payload have been
  promoted to stable contracts with snapshot coverage.
- Two production-shaped LLM providers (OpenAI-compatible, Anthropic)
  ship with retry, streaming, structured-output validation, cost
  accounting, fan-out, and a (gated) live CI lane.
- Subagent pool with bounded concurrency, cancellation, and
  LLM-driven synthesis exists with deterministic tests.
- Threat model, why-safecode, compare, troubleshooting, providers docs
  are all merged.

Weaknesses that block calling this product "shipped":

- **Distribution is unverified.** `sac release publish` exists with a
  dry-run mode and gates a real run behind `SAFECODE_PUBLISH=1`. No
  evidence of an actual PyPI upload, signed artifact, or `pipx install
  safecode-agent` working end to end. The implementation uses
  `cosign` or `gpg` detached signing, not Sigstore as the DoD requires.
- **VS Code extension does not exist as a published artifact.** Only an
  in-tree manifest describing the JSON-RPC transport plus a hidden
  `sac api jsonrpc` command. No `vscode-extension/` directory in this
  repository; no extension package on the VS Code Marketplace; no
  in-editor diff preview, approval prompt, or journal tail.
- **`sac fix` and stack-aware quickstart never landed.** The
  v3.1.2–v3.1.5 task IDs (`sac-fix-command`, `stack-aware-quickstart`,
  `onboarding-provider-wizard`, `progress-indicator`,
  `repo-recency-signal`) are absent from the implemented train.
- **MCP read execution is not promoted.** The v3.3.0–v3.3.6 work shipped
  a stdio JSON-RPC transport, static schema, classification gate, and
  adversarial tests — but the read-only stdio adapter is explicitly
  not wired into `MCPReadOnlyRunner`, write proposals do not execute
  end-to-end, no `mcp lifecycle`, no per-server scopes, no `sac mcp
  doctor`. MCP remains experimental.
- **Sandbox real execution is not promoted.** Docker, Seatbelt,
  Bubblewrap all carry `execute(...)` paths with `shell=False`, but
  the planner-vs-executor split that the prior roadmap called for was
  not completed, no per-backend promotion preflight exists, and the
  default and documented recommendation remains Noop. Cross-backend
  security evals (v2.4.3) have not been re-run as a promotion gate.
- **Loop eval CI is still advisory.** `continue-on-error: true` in
  `loop-eval`. The DoD requires it be promoted to blocking after one
  clean cycle; no such promotion happened.
- **Live-provider CI lane is scaffolded.** The job exists, is gated on
  `vars.ENABLE_LIVE_LLM_TESTS == 'true'`, and is `continue-on-error:
  true`. No evidence of "one full release train of clean live runs"
  in the repo.
- **Performance baseline is absent.** No `sac eval bench` command,
  no `.sac/metrics.jsonl` emission, no documented context-pack budgets.
- **Per-stack tutorials are absent.** Python is covered through the
  demo workflow; TypeScript and Go have no first-hour tutorial.

The verdict in one line:

> v3.6.6 is **commercial v1 documentation cut**: the contracts, threat
> model, and landing docs are present, but the actual distribution,
> editor surface, real-MCP execution, real-sandbox promotion, and
> performance evidence have not been delivered.

---

## 2. Definition-Of-Done audit

Each DoD bullet from `product-commercialization-roadmap.md` Section 8.

### 2.1 Functional

| DoD criterion | Status | Evidence / Notes |
|---|---|---|
| Autopilot loop (`sac agent run`) drives a multi-step task to completion or stop-for-user, deterministically resumable | **shipped** | v3.1.0 (`sac agent run`), v3.1.1 (`sac agent resume <session_id>`). Tested under mock + scripted client. |
| `sac fix` and `sac edit --retry-from-last-failure` work on real repos in three stacks | **partially shipped** | `--retry-from-last-failure` shipped v3.1.1. `sac fix` **not shipped** (T-3.1.2-A absent from the train). "Real repos in three stacks" never demonstrated. |
| MCP read calls execute against a real stdio JSON-RPC server through SafeCode's audit boundary; write proposals gate at approval | **experimental / not shipped** | v3.3.0–v3.3.6 shipped the stdio transport and a *not-wired* read-only adapter. `MCPReadOnlyRunner` is unchanged. MCP write proposal end-to-end (T-3.3.3-A) **not shipped**. MCP lifecycle (T-3.3.1-A) **not shipped**. Per-server scopes (T-3.3.2-A) **not shipped**. MCP doctor (T-3.3.4-A) **not shipped** under that ID. Per-server contract not promoted. |
| Two production LLM providers (OpenAI-compatible, Anthropic) supported with retry, streaming, cost accounting | **shipped** | v3.2.0–v3.2.4. Retry, streaming, structured-output validation, cost accumulator, fan-out present and tested. |
| Subagent pool supports bounded concurrency with synthesis | **shipped** | v3.4.0 pool (default max 2), v3.4.1 cancellation, v3.4.2 synthesis, v3.4.3 payload v2 promoted to stable contract. |

### 2.2 UX

| DoD criterion | Status | Evidence / Notes |
|---|---|---|
| All daily commands offer documented `--json` output | **shipped** | v3.1.0 `CLIJSONResponse` + `--json` on `ask`, `edit`, `apply`, `run`, `doctor`, `version`, `release preflight`, `agent run`. |
| Onboarding wizard recommends provider/model/stack without enabling network unless the user confirms | **not shipped** | T-3.1.3-B (`sac setup --wizard`) absent. `sac quickstart` exists (v2.7.5) but is not stack-aware (T-3.1.3-A absent). |
| Interactive TUI and VS Code extension cover the daily loop | **partially shipped / scaffolded** | TUI: `sac tui interactive` ships a Rich Live snapshot (v3.5.2), not Textual, and does **not** cover the daily loop (no approval prompt, no plan view, no journal-tail history beyond a render). VS Code extension: only manifest + `sac api jsonrpc` stub; **no published extension**, no diff preview, no in-editor approval. |
| Error messages include actionable next steps | **partially shipped** | `Diagnostic.hints` (v2.8.0) plus `sac doctor` next-step hints. Not systematic across every command. |

### 2.3 Safety / security

| DoD criterion | Status | Evidence / Notes |
|---|---|---|
| Threat model covers four personas + lives in `docs/security/` | **shipped** | `docs/security/threat-model-v3.6.md` covers nine personas (exceeds requirement). |
| Semi-annual security review cadence documented | **shipped** | Threat model declares 2026-12-01 or v4.0 as next review. |
| Sandbox executes only on Docker/Seatbelt/Bubblewrap after each backend passes its own evals; Noop remains the default and is explicitly labeled | **partially shipped** | `execute(...)` paths exist with `shell=False` in all three backends. The promotion gate the prior roadmap mandated (planner→executor split + per-backend preflight + re-running cross-backend evals as a promotion check) does **not** exist. Default and documented recommendation remain Noop. Sandbox real execution remains effectively "preview." |
| Approval atomicity and project-binding remain invariant | **shipped** | No regression in `sandbox/approvals.py`. v3.0 public contract holds. |

### 2.4 Reliability

| DoD criterion | Status | Evidence / Notes |
|---|---|---|
| LLM retry covers transient 429/503/network failures; mocked tests cover ≥ 8 failure modes | **shipped** | `tests/test_llm_retry.py` covers URLError + HTTP 429/503; retry-after; jitter; backoff; max-attempt cap. |
| Live-provider CI lane has run cleanly for one full release train | **scaffolded** | Job exists, gated on `vars.ENABLE_LIVE_LLM_TESTS == 'true'`, `continue-on-error: true`. No evidence in repo of run-history meeting the bar. |
| Loop eval CI gate promoted from advisory to blocking | **not shipped** | `loop-eval` job still has `continue-on-error: true`. Promotion never happened. |
| All public-contract snapshots match across the matrix | **shipped** | Snapshot tests green; provider + subagent v2 + tool registry + audit + sandbox + eval-trace snapshots all enforced. |

### 2.5 Performance

| DoD criterion | Status | Evidence / Notes |
|---|---|---|
| Live-session metrics emitted to `.sac/metrics.jsonl` | **not shipped** | No metrics writer; only per-replay `PerformanceBudget`. |
| Context-pack p50 size budget documented per language preset | **not shipped** | `ContextBudgetManager` exists, but there is no per-language preset table and no `docs/` page on budgets. |
| Bench suite (`sac eval bench`) baseline captured at v3.6.0 and tracked | **not shipped** | No `sac eval bench` subcommand. No baseline file. |

### 2.6 Documentation

| DoD criterion | Status | Evidence / Notes |
|---|---|---|
| `docs/why-safecode.md`, `docs/compare.md`, `docs/providers.md`, `docs/troubleshooting.md`, three per-stack tutorials linked from README | **partially shipped** | First four docs **shipped** (v3.2.6 + v3.6.5). Per-stack tutorials: only the existing Python-flavored demo workflow + `docs/mvp-user-guide.md`. **No TypeScript or Go tutorial.** |
| Public contracts page reflects every promoted surface | **shipped** | Provider contract added v3.2.6; subagent v2 payload added v3.4.3. IDE bridge and MCP correctly labeled experimental. |
| One end-to-end "first hour" tutorial per stack | **partially shipped** | Same gap as above — only one stack covered. |

### 2.7 Release / support

| DoD criterion | Status | Evidence / Notes |
|---|---|---|
| Sigstore-signed wheels published to PyPI | **scaffolded / docs-only** | `sac release publish --sign` exists; uses **cosign or gpg detached signature**, not Sigstore. No actual PyPI upload has occurred. `pyproject.toml` declares `name = "safecode-agent"` but the package is not on PyPI. |
| `pipx install safecode-agent` works on macOS, Linux, and Windows (smoke) | **not shipped** | Cannot work; package not on a public index. No `brew` formula or tap in this repo. |
| `sac doctor` warns when a newer tag is available (opt-out via env) | **shipped** | v3.6.1 `Doctor._update_check_diagnostic` queries PyPI over HTTPS; offline → SKIP; never raises; no telemetry. Note: because the package is not actually on PyPI, the check currently returns SKIP. |
| Versioning policy documented (minor adds experimental, patch never changes contract, major reserved for contracts) | **partially shipped** | Implicit in `docs/release_roadmap_v0_1_to_v1_0.md`, `docs/public-contracts.md`, and the train discipline. No dedicated `docs/versioning-policy.md`. |
| Release cadence: one minor every 4–6 weeks; one patch as needed; one security review per train | **docs-only / aspirational** | Stated in roadmap; cadence not externally observable since no public release stream exists. |

---

## 3. Surfaces classified by contract status

| Surface | v3.6.6 contract status | Notes |
|---|---|---|
| Config precedence + lowering rules | stable (v3.0) | Snapshot in `tests/snapshots/contracts/config_defaults.json`. |
| Pending patch format (`PatchProposal`/`PatchBlock`) | stable (v3.0) | Snapshot. |
| Audit event hash chain | stable (v3.0) | Snapshot + anchor invariant. |
| Sandbox propose/preflight/approve/execute/result | stable (v3.0) | Snapshot. |
| Local tool registry (`ToolSpec`, schema version `"1"`) | stable (v3.0, v2.9.8) | Snapshot. |
| Eval trace (`LoopStepTrace`/`LoopEvalTrace`) | stable (v3.0) | Six fixture snapshots. |
| Recommended CLI workflow | stable (v3.0) | Daily-command list documented. |
| Audit anchor + outside-project trust root | stable (v3.0) | Threat model section. |
| LLM provider contract (`docs/providers.md` + provider snapshot) | **stable (v3.2.6)** | Provider snapshot file lives at `tests/snapshots/contracts/provider_contract_schema.json`. |
| Subagent dispatch payload v2 | **stable (v3.4.3)** | `CURRENT_PAYLOAD_VERSION=2`, both v1 and v2 supported. |
| `--json` CLI envelope (`CLIJSONResponse`) | shipped but **not formally promoted** | Behavior is documented in source; consider promoting in v3.7.x. |
| `sac api jsonrpc` IDE/LocalAPI bridge | **experimental** | `CONTRACT_VERSION="1"` declared in code, not promoted. |
| MCP stdio transport, `StdioReadOnlyAdapter`, schema store merge | **experimental** | Not wired into default runner. |
| TUI (`sac tui interactive`) | **experimental** | Not interactive in the loop sense. |
| OTel exporter | **experimental, opt-in** | `SAFECODE_OTEL_EXPORTER` disabled by default. |
| `sac report html` | shipped but **not formally promoted** | Deterministic; redacted. |
| `sac release publish` | shipped but **never run for real** | Real publish gated on `SAFECODE_PUBLISH=1`; no recorded run. |
| Real sandbox execution (Docker/Seatbelt/Bubblewrap) | **preview** | Code present, default recommendation still Noop. |

---

## 4. Gaps that must be addressed before v4.0

Ranked by blocking impact for a "commercial v1 actually shipped" claim.

1. **Distribution actually performed.** A signed wheel must be uploaded
   to PyPI; `pipx install safecode-agent` must succeed end to end on at
   least macOS + Linux; the signing mechanism must match what the DoD
   and threat model claim (either swap implementation to Sigstore or
   correct the docs to say "detached cosign/gpg signature").
2. **VS Code extension as a real artifact.** Either publish a working
   extension (Marketplace or VSIX) that consumes `sac api jsonrpc` for
   the daily loop, or remove the Marketplace claim from the DoD.
3. **MCP read execution promoted (or explicitly deferred).** Wire
   `StdioReadOnlyAdapter` into `MCPReadOnlyRunner`, land per-server
   scopes, lifecycle, and `sac mcp doctor`. Promote read execution to
   the public contracts. If this slips, MCP must remain explicitly
   experimental and the DoD bullet must be deleted.
4. **`sac fix` and stack-aware quickstart.** P0 product UX still missing
   from v3.1.x; without these the "agent that fixes failing tests"
   selling point is hand-rolled by the user.
5. **Loop eval blocking promotion.** The advisory CI gate has been
   advisory long enough to either have proved stable (promote) or be
   acknowledged as unreliable (rewrite the fixtures).
6. **Live-provider CI lane recorded.** Either prove the lane has run
   green for a release train and promote it from `continue-on-error:
   true` to required, or treat it as advisory and document so.
7. **Performance baseline.** `sac eval bench` with a baseline file and
   live-session metrics writer must exist before the "scales for real
   work" claim is defensible.
8. **Per-stack tutorials (TypeScript, Go).** Without these the
   product-readiness narrative leans entirely on Python users.
9. **Sandbox executor promotion criteria.** Without an explicit
   promotion gate, "Docker / Seatbelt / Bubblewrap" remain marketing
   words attached to code paths nobody has audited.
10. **Versioning policy doc.** A single page in `docs/` that says what
    a patch/minor/major bump does is required for users to accept the
    contract churn budget.

---

## 5. Gaps that should remain deferred or out of scope

Each item below would *expand* the threat model or the surface area in
ways inconsistent with "local-first, safety-first." They are explicit
non-goals through v4.0.

- Cloud / team / SaaS backend.
- Centralized policy server, multi-user workspaces.
- External plugin ABI for `ToolSpec`.
- Telemetry enabled by default. OTel must stay opt-in.
- "Auto-fix on save" or any non-interactive auto-write / auto-execute
  default. Approvals must remain the default.
- Signed audit anchors that depend on an external CA.
- Weakening of redaction at the journal boundary, subagent results, or
  context selection.
- Removal of the project-config-cannot-lower-user-policy invariant.
- Replacing the local patch grammar with unified-diff as the default
  (it may exist as an opt-in adapter; the default contract is frozen).

---

## 6. Recommended next stage shape

Based on the above, the next stage should be **v3.7.x through
v4.0-prep**. v4.0 itself should be reserved for any unavoidable public
contract change and should not become a feature catch-all. Concrete
batches are defined in
`docs/version-plans/v3.7-to-v4.0-product-roadmap.md`.

Key sequencing constraints:

- Workflow gap closure (skipped v3.1.x UX) precedes anything else,
  because `sac fix` and stack-aware quickstart materially change the
  product story used in every later doc and tutorial.
- MCP hardening should land before promoting the IDE JSON-RPC contract,
  because the IDE bridge re-uses the MCP transport pattern and the
  promotion criteria must be consistent.
- Real distribution (PyPI + signing) should land before VS Code
  publishing, because the extension's documented install flow assumes a
  reachable `sac` binary in a known package.
- Performance baseline and loop-eval-blocking promotion should land
  before any "scales / reliable" marketing claim.
- Sandbox executor promotion preflight is optional for v4.0; it can ship
  as v4.0+1 if the promotion criteria are not yet met. Do not promote
  any sandbox backend just to hit a date.

---

## 7. Open questions for v4.0 contract scope

These are *decision points*, not commitments.

- Should the `--json` envelope (`CLIJSONResponse`) be promoted to a
  stable contract? Recommendation: yes, at v3.7.x docs cut, with a
  snapshot.
- Should `sac report html` become a stable contract? Recommendation:
  no — keep it as a useful but unpromoted surface to allow future
  templating changes.
- Should MCP read execution become a stable contract once wired?
  Recommendation: yes, but only after one full release train of clean
  runs against at least two real MCP servers, and with the per-server
  scope vocabulary explicitly documented.
- Should the IDE JSON-RPC contract be promoted? Recommendation: only
  after a published VS Code extension has consumed it for one release
  cycle; the in-tree `CONTRACT_VERSION="1"` is a placeholder.
- Should the local patch grammar gain a unified-diff adapter?
  Recommendation: only as an opt-in `experimental` flag; never replace
  the v3.0 grammar.
- Should any sandbox backend promotion change the default recommended
  backend? Recommendation: **no**, even after promotion. Noop should
  remain the default to keep the install-and-run path safe; users
  opt into Docker/Seatbelt/Bubblewrap explicitly.

The proposed v4.0 contract churn budget is **at most two new stable
contracts** (most likely `--json` envelope + MCP read execution) and
**zero breaking changes** to existing v3.0 contracts.
