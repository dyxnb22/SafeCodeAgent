# Commercial v1 Readiness Audit - v3.11.x

Status: v4.0-prep audit. No runtime change in this audit.
Baseline: tag `v3.11.2`, package version `3.11.2`, branch `main`.
Authoring date: 2026-06-04.

This document re-audits current HEAD against the v4.0 readiness goals in
`docs/version-plans/v3.7-to-v4.0-product-roadmap.md` Section 3. It uses the
same classification vocabulary as
`docs/commercial-v1-readiness-audit-v3.6.6.md`: `shipped`, `partially shipped`,
`experimental`, `scaffolded`, `docs-only`, `not shipped`, and `deferred`.

Evidence is implementation-first. A doc, roadmap row, or version note does not
upgrade a criterion to shipped unless the code path, tests, and release evidence
exist in the repository.

Sources read for this audit:

- `.claude/skills/current/SKILL.md`
- `.claude/skills/shared/core-runtime.md`
- `docs/version-plans/v3.7-to-v4.0-product-roadmap.md`
- `docs/commercial-v1-readiness-audit-v3.6.6.md`
- `docs/public-contracts.md`
- `docs/versioning-policy.md`
- `docs/version_implementation_matrix.md`
- `docs/version-notes/v3.7.0-sac-fix-stack-quickstart.md` through
  `docs/version-notes/v3.11.2-sandbox-executor-preflight.md`
- `README.md`, `docs/install-update.md`, `docs/security/threat-model-v3.6.md`
- `tests/test_public_contract_snapshots.py`,
  `tests/snapshots/contracts/`

---

## 1. Executive verdict

v3.11.x is a materially stronger v4 candidate than v3.6.6: `sac fix`,
stack-aware quickstart, setup wizard, progress display, repo-recency ranking,
MCP read execution, benchmark snapshots, opt-in metrics, context-budget docs,
TypeScript/Go tutorials, policy diff, and sandbox executor preflight have all
landed with tests.

The commercial-v1 story is still not fully shipped. PyPI distribution is not
proven by repository evidence, the VS Code extension has not completed a VSIX
or marketplace release cycle, loop-eval and live-provider CI remain advisory,
and real Docker/Seatbelt/Bubblewrap execution remains preview until each local
backend passes executor preflight plus explicit environment opt-in.

v4.0 should therefore be a contract/documentation cut, not a product-claim
escalation. The safe path is:

- Preserve all v3.0 public contract snapshot shapes.
- Promote at most the surfaces that already have docs, snapshots, tests, and
  release history.
- Keep Noop as the default sandbox recommendation.
- Explicitly defer distribution, IDE, loop-eval, live-provider, and sandbox
  real-execution claims that do not yet have production evidence.

---

## 2. v4.0 readiness goals

Each criterion below is from Section 3 of the v3.7-to-v4.0 roadmap.

| # | v4.0 readiness goal | Status | v4.0 disposition | Evidence / notes |
|---|---|---|---|---|
| 1 | A signed wheel is on PyPI; `pipx install safecode-agent` works on macOS + Linux; Windows works at smoke level. | **partially shipped** | **deferred after v4.0** | Release publish and TestPyPI/PyPI commands exist; detached cosign/gpg signing is documented. There is no repository evidence of an actual PyPI upload, signed public artifact, or OS install smoke. Do not claim product distribution shipped at v4.0. |
| 2 | The signing mechanism named in the threat model and in `sac release publish` matches the implementation. | **shipped** | not a blocker | v3.9.0 chose detached cosign/gpg signatures and updated implementation docs plus threat model. Sigstore/Rekor claims were corrected. |
| 3 | `sac doctor` correctly identifies stale installs against PyPI. | **shipped** | not a blocker | v3.6.1 added the PyPI update diagnostic; offline, 404, and timeout paths skip safely and never raise. |
| 4 | `sac fix`, stack-aware `sac quickstart`, and `sac setup --wizard` ship as documented, with `--json` outputs. | **shipped** | not a blocker | v3.7.0/v3.7.1 shipped the commands. `sac fix` and daily commands use `CLIJSONResponse`; docs and tests cover the machine-readable envelope. |
| 5 | MCP read execution is either wired end to end and promoted, or explicitly removed from the DoD and labeled deferred. | **shipped** | not a blocker | v3.8.0 wired stdio read execution behind opt-in, v3.8.1 added scopes/doctor, and v3.8.2 promoted MCP read execution with `mcp_read_contract.json`. MCP write execution/lifecycle remain experimental. |
| 6 | A published VS Code extension consumes `sac api jsonrpc` for the daily loop, or the marketplace promise is removed from the DoD. | **partially shipped** | **deferred after v4.0** | The `vscode-extension/` tree and manifest parity tests exist, but VSIX build was deferred and no marketplace or release-cycle consumption evidence exists. Keep IDE JSON-RPC experimental at v4.0. |
| 7 | Loop-eval CI is blocking; live-provider CI lane has at least one recorded green train. | **partially shipped** | **deferred after v4.0** | v3.10.1 intentionally recorded that both lanes remain advisory because no clean train is available in repo evidence. Do not promote either claim at v4.0. |
| 8 | Performance baseline (`sac eval bench`) lives in CI; live-session metrics are written to `.sac/metrics.jsonl` opt-in. | **partially shipped** | **deferred after v4.0** | `sac eval --mode bench`, bench snapshots, and opt-in metrics are implemented. CI promotion evidence is not present. Metrics remain local and disabled by default. |
| 9 | Three per-stack tutorials (Python, TypeScript, Go) link from README. | **shipped** | not a blocker | README links TypeScript and Go first-hour tutorials; the Python flow remains covered by the MVP user guide and demo workflow. |
| 10 | `docs/versioning-policy.md` exists; the v4.0 contract churn budget is honored. | **shipped** | not a blocker | The policy doc exists, README links it, and tests pin patch/minor/major semantics plus the v4.0 budget: at most two new stable contracts and zero v3.0 breaking changes. |

---

## 3. Contract promotion candidates

| Candidate | Current status at v3.11.x | Recommendation for v3.99.1 |
|---|---|---|
| CLI `--json` envelope | Stable since v3.7.2 with docs and snapshot. | Treat as already promoted; preserve unchanged. |
| MCP read execution | Stable since v3.8.2 with docs and snapshot. | Treat as already promoted; preserve unchanged. |
| IDE JSON-RPC | Experimental; VSIX and release-cycle consumption missing. | Defer. |
| TUI interactive | Frozen experimental since v3.9.2. | Reject/defer stable promotion. |
| `sac report html` | Implemented and tested, but not snapshot-promoted. | Defer. |
| Sandbox real-execution opt-in | Preflight and env gates implemented; backend pass evidence is host-local and backend-specific. | Defer stable promotion unless v3.99.1 finds stronger evidence. |

---

## 4. v4.0 blockers and deferrals

No item above requires blocking v4.0 if v4.0 is scoped as a contract cut with
honest docs. The following product-readiness claims are deferred after v4.0:

- Public PyPI distribution and OS install smoke.
- Published VS Code extension or VSIX release-cycle evidence.
- Blocking loop-eval CI.
- Recorded green live-provider train.
- CI-hosted performance baseline evidence.
- Stable sandbox real-execution contract beyond the existing v3.0 lifecycle
  contract.

The following are rejected from the v4.0 DoD unless a future evidence pass
reopens them:

- Promoting TUI output or interaction format as a stable automation contract.
- Promoting `sac report html` as a stable public contract in v4.0.
- Promoting IDE JSON-RPC based on docs or manifest parity alone.

---

## 5. Final v4 readiness position

v4.0 can ship honestly as a **contract cut** if it:

1. Adds no more than two new stable contracts at v4.0.
2. Makes zero breaking changes to v3.0 public contracts and snapshot shapes.
3. Keeps the default LLM provider as `mock`.
4. Keeps telemetry disabled by default.
5. Keeps Noop as the default sandbox recommendation.
6. Leaves IDE, TUI, HTML report, live-provider behavior, loop-eval blocking, and
   sandbox real-execution promotion claims explicit rather than implied.
