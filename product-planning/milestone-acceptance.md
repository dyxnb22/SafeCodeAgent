# Milestone Acceptance Gates

**Implementation status (v1.9):** Executable contracts through v1.9 are implemented; see `.agents/context/progress.json` for live stage state.
Every stage version in `version-roadmap.md` has a hard acceptance gate.
A stage is only "done" when **all five gate dimensions are satisfied**:

1. **Engineering acceptance** — all tests pass, all new modules
   covered, no regression in the full pytest suite.
2. **Product acceptance** — the demo described in `version-roadmap.md`
   runs end-to-end on a clean checkout.
3. **Security acceptance** — every existing safety invariant still
   holds, plus any new invariants introduced in the stage.
4. **Evaluation acceptance** — relevant eval suites pass at or above
   baseline.
5. **Demo / interview acceptance** — the stage is explainable in
   under five minutes with concrete artifacts.

A stage may carry forward at most three documented "yellow" risks
into the next stage. Anything else must be closed before the gate
passes. Yellow risks must be listed in `decision-log.md`.

This document is the single source of truth for "is stage `vX.Y`
done?". If `version-roadmap.md` and this file disagree, this file
wins; reconcile in the next PR.

---

## Gate Dimensions Defined

### Engineering acceptance

For each stage:

- `PYTHONPATH=src python3 -m pytest -q` exits 0 on a clean checkout
  with the mock LLM provider.
- New modules introduced in the stage have a unit-test file with at
  least the listed coverage points.
- No new module exposes public symbols not referenced in either a
  test, a CLI command, or another internal module.
- `scripts/verify-package.py` (existing) still passes.

### Product acceptance

For each stage:

- The demo command listed under "Completion demo" in
  `version-roadmap.md` runs on a fresh `uv sync` clone.
- A 60-second written walk-through is in
  `interview-master-narrative.md` (or updated there).
- The demo produces at least one artifact a reviewer can open
  (Markdown report, trace dashboard, JSON timeline, or audit chain).

### Security acceptance

For each stage:

- No new code path lets the model directly mutate files, run
  commands, push branches, or call the network.
- Every new write path has: preview, approval, audit event,
  rollback or compensating action.
- Tool classification is local; no MCP-server-claimed metadata
  drives security decisions.
- Retrieved content is treated as data; explicit prompt-injection
  eval cases pass.
- Default config posture is fail-closed for new capabilities.

### Evaluation acceptance

For each stage where eval suites apply (v1.1 and later):

- Relevant eval suites under `tests/enterprise/eval/` pass.
- Baseline files in `tests/enterprise/eval/baselines/` exist and
  are referenced by the suite.
- Any baseline change is in a separate PR with explicit
  `--update-baseline` invocation noted in the commit message.

### Demo / interview acceptance

For each stage:

- `interview-master-narrative.md` contains a section explaining the
  stage in interview-ready form.
- The demo is recordable in under five minutes from a clean clone
  (excluding `uv sync`).
- One screenshot or rendered artifact is checked into
  `examples/enterprise/demos/<stage>/`.

---

## Stage Gates

### v1.0 Enterprise Branch Reset and Planning

**Engineering acceptance**
- `tests/enterprise/test_namespace_import.py` passes.
- `tests/enterprise/test_planning_present.py` passes.
- Full suite green.

**Product acceptance**
- A reviewer can navigate `product-planning/` and
  `enterprise-docs/` and find every planning doc through one of the
  two `README.md` files.
- No planning file is empty or has placeholder text.

**Security acceptance**
- No legacy docs restored.
- No `src/` modifications outside the new
  `src/safecode/enterprise/` namespace skeleton.
- No new dependencies in `pyproject.toml`.

**Evaluation acceptance**
- Not applicable (no eval suites yet).

**Demo / interview acceptance**
- `interview-master-narrative.md` exists and covers the project
  premise.

**Yellow-risk policy**
- None allowed; this is the planning stage.

**Carry-forward risks accepted into next stage**
- None.

---

### v1.1 RAG Security Knowledge Base MVP

**Engineering acceptance**
- All tests under `tests/enterprise/rag/` and
  `tests/enterprise/eval/test_retrieval_quality.py` pass.
- `sac enterprise retrieve "<query>"` returns JSON citations on
  the fixture knowledge sources.
- Hybrid retrieval is deterministic on the mock embedding backend.

**Product acceptance**
- Running the demo command on
  `examples/enterprise/knowledge_sources.yaml` produces ≥1 cited
  policy and ≥1 cited code chunk for the SQL-injection seed query.
- Each citation includes source path, line range, score, selection
  reason, permission verdict, and freshness.

**Security acceptance**
- Permission filter drops restricted chunks even when score is
  higher than allowed ones (test).
- Secret-bearing fixture lines do not appear in retrieval output
  (redaction test).
- No retrieval call performs network I/O in the default lane.

**Evaluation acceptance**
- `tests/enterprise/eval/baselines/retrieval_v1_1.json` exists.
- Recall@5 ≥ baseline − 2 percentage points on every retrieval
  case.

**Demo / interview acceptance**
- A short Markdown walk-through under
  `examples/enterprise/demos/v1.1/retrieve_walkthrough.md` shows the
  command, inputs, and the cited output.

**Yellow-risk policy**
- Allowed yellow risks:
  - BM25-ish scorer is hand-rolled and may need replacement at v1.6.
  - No reranker yet; acceptable until PR review baselines fail.
- Anything else must close before the gate.

---

### v1.2 LangGraph Security Workflow MVP

**Engineering acceptance**
- All tests under `tests/enterprise/workflow/` pass under both
  `WORKFLOW_RUNTIME=local` and `WORKFLOW_RUNTIME=langgraph` (where
  langgraph is installed via the `enterprise` extra).
- Resume test passes: workflow state stored after each node,
  re-entered without re-running prior nodes.

**Product acceptance**
- `sac enterprise workflow run --task pr_review --input
  fixtures/pr_001/` produces `report.md` and `state.json`.
- `sac enterprise workflow run --resume <run_id>` continues a paused
  workflow.
- `sac enterprise approval` commands operate on real approval
  records.

**Security acceptance**
- High-risk plan paths cannot proceed past `approval_gate`.
- Approvals are single-use; second use raises typed error.
- No node performs writes, commands, or network calls directly;
  only through approved tool adapters.

**Evaluation acceptance**
- Retrieval eval still green (no v1.1 regression).
- New workflow happy-path tests are deterministic.

**Demo / interview acceptance**
- Walk-through showing a workflow pausing at approval and resuming
  after a CLI approve.
- `interview-master-narrative.md` updated with the LangGraph rationale.

**Yellow-risk policy**
- Allowed yellow risks:
  - LangGraph version pinning may force an upgrade.
  - HITL inbox is CLI-only.

---

### v1.3 Tool/MCP Enterprise Connector Layer

**Engineering acceptance**
- All connector tests pass.
- Tool registry contains the six native tools + the MCP adapter.
- Semgrep and pip-audit normalizers tested against fixture JSON.

**Product acceptance**
- Workflow consumes one of: a PR fixture, a Semgrep run, or an
  issue file, and produces typed evidence in the trace.
- Offline mode is the default; live mode is opt-in via existing
  network policy.

**Security acceptance**
- MCP server-claimed `category` is ignored (test).
- All write-capable connectors default to `BLOCK` until allowlisted
  by policy.
- Connector errors do not echo credentials or full request bodies.

**Evaluation acceptance**
- Tool-classification adversarial eval suite (added in v1.6.4)
  passes when run against v1.3 connectors. (Suite formally lands
  in v1.6 but is exercised early.)

**Demo / interview acceptance**
- Walk-through showing the same workflow consuming a fixture PR,
  a Semgrep finding, and an issue file.

**Yellow-risk policy**
- Allowed yellow risks:
  - Jira/Linear is fixture-only; no live API yet.
  - Networked scanner APIs not supported.

---

### v1.4 Security Governance, RBAC, Approval Engine

**Engineering acceptance**
- Policy resolver tests cover precedence and no-weakening.
- RBAC permission map test asserts every action × role pair.
- Approval engine decision matrix test passes.

**Product acceptance**
- A run with a `developer` role attempting a PR comment ends with
  `policy_block` and the workflow finalizes in a "blocked" state.
- A `maintainer` role on the same run gets a `GATE` decision and
  can approve via CLI.

**Security acceptance**
- Project-level policy file attempting to upgrade `github_write` to
  `AUTO` is rejected and emits `policy.project_override_blocked`.
- Audit chain unbroken across the workflow run.
- Single-use grants enforced.

**Evaluation acceptance**
- Existing suites still green.

**Demo / interview acceptance**
- Walk-through showing the same fixture run twice: once as
  `developer` (blocked), once as `maintainer` (approved + executed).

**Yellow-risk policy**
- Allowed yellow risks:
  - No time-bound grants yet.
  - No SSO; user identity comes from local policy file.

---

### v1.5 AgentOps Observability and Trace Dashboard

**Engineering acceptance**
- Trace emitter tests pass; events have stable ids.
- Timeline JSON round-trips; renderer produces all required
  sections.
- Redaction strict-mode is the default and tested.

**Product acceptance**
- `sac enterprise trace show <run_id>` produces a Markdown report
  containing Summary, Timeline, Citations, Tool Calls, Approvals,
  Validation, Cost, Safety Invariants, Failures.
- Trace JSON is consumable by the evaluation runner introduced in
  v1.6.

**Security acceptance**
- Strict redaction is the default for export.
- Debug profile is reachable only when policy bit
  `allow_debug_traces=true` is set.
- No raw prompts or full file contents appear in default trace
  output (regex-based test).

**Evaluation acceptance**
- Trace artifacts can be loaded by the eval runner without
  contract drift.

**Demo / interview acceptance**
- A rendered trace dashboard is committed under
  `examples/enterprise/demos/v1.5/trace_dashboard.md`.

**Yellow-risk policy**
- Allowed yellow risks:
  - No OpenTelemetry export.
  - Trace file rotation/retention is manual.

---

### v1.6 Evaluation and Regression Platform

**Engineering acceptance**
- `pytest tests/enterprise/eval -q` passes.
- Eval runner is deterministic on the mock provider.
- Each suite has a baseline JSON checked in.

**Product acceptance**
- `sac enterprise eval run --suite all` runs all suites and writes
  `.sac/enterprise/eval/latest.md`.
- Updating a baseline requires `--update-baseline`.

**Security acceptance**
- Prompt-injection cases all pass.
- Tool-classification adversarial cases all pass.
- No eval bundle contains debug-mode trace artifacts.

**Evaluation acceptance**
- Baselines published and referenced.
- CI lane blocks merges that regress baselines beyond the policy
  threshold.

**Demo / interview acceptance**
- A 5-minute walk-through of the eval dashboard, including how to
  read a regression.

**Yellow-risk policy**
- Allowed yellow risks:
  - Live-provider eval lane optional and manual.

---

### v1.7 PR Security Review MVP

**Engineering acceptance**
- All PR review tests pass.
- Workflow consumes a PR fixture and emits a risk-ranked report.

**Product acceptance**
- Demo run on a fixture PR with a known SQL-injection pattern
  produces a report with severity tier `high`, ≥1 policy citation,
  ≥1 code citation.
- Optional draft comment writes to a fixture file in offline mode;
  live mode requires approval and `network=on`.

**Security acceptance**
- PR comment writes only fire after explicit approval.
- Prompt-injection cases from PR bodies pass.
- No comment body contains secrets from the diff.

**Evaluation acceptance**
- `pr_review` eval suite passes at baseline.

**Demo / interview acceptance**
- 5-minute demo: load PR fixture → report → optional draft comment.
- Walk-through saved under
  `examples/enterprise/demos/v1.7/pr_review.md`.

**Yellow-risk policy**
- Allowed yellow risks:
  - Live GitHub mode optional and gated.
  - Limited to GitHub; no GitLab/Bitbucket.

---

### v1.8 Vulnerability Remediation Workflow

**Engineering acceptance**
- Remediation tests pass.
- Rollback test asserts working tree restored on rejection or
  validation failure.

**Product acceptance**
- Demo: Semgrep finding → vulnerable code located → patch proposal
  → checkpoint → approval → patch applied → revalidation → final
  report.
- Rejection path produces an audit event and leaves the tree
  unchanged.

**Security acceptance**
- Patch apply gated by approval; no automatic write.
- Validation cannot disable tests or pass with regressions.

**Evaluation acceptance**
- Remediation eval suite passes at baseline.

**Demo / interview acceptance**
- 5-minute demo, walk-through under
  `examples/enterprise/demos/v1.8/remediation.md`.

**Yellow-risk policy**
- Allowed yellow risks:
  - Patch suggestions limited to Python and YAML; broader language
    coverage in later stages.

---

### v1.9 Enterprise Beta Hardening

**Engineering acceptance**
- Multi-tenant tests pass.
- Evidence export tests pass.
- Performance budget test asserts PR review fixture < 30 s on mock
  provider on CI.

**Product acceptance**
- `sac enterprise evidence export --run <id>` produces a zip with
  trace, citations, approvals, audit chain, validation outputs.
- Two-project run shows tenant boundary in retrieval and audit.

**Security acceptance**
- Tenant isolation enforced in RAG and audit.
- Evidence export contains no debug-mode artifacts unless policy
  explicitly enables them.

**Evaluation acceptance**
- All suites pass at baseline.
- Performance budgets met.

**Demo / interview acceptance**
- Beta-readiness summary checked in under
  `examples/enterprise/demos/v1.9/beta_summary.md`.

**Yellow-risk policy**
- Allowed yellow risks:
  - No web dashboard yet.
  - Compliance evidence covers SOC2/secure-SDLC categories only;
    no industry-specific (HIPAA/PCI) profiles.

---

### v2.0 Enterprise Release Candidate

**Engineering acceptance**
- All suites pass.
- Contract snapshot test green.
- `scripts/verify-package.py` green.

**Product acceptance**
- All four flagship workflows runnable from CLI on a clean clone.
- Demo bundle includes PR review, remediation, evidence export,
  and a full trace dashboard.

**Security acceptance**
- External-style security review notes filed and remediated.
- No open high-severity finding.
- Policy posture documented per deployment profile.

**Evaluation acceptance**
- Eval dashboard published; baselines tagged with the RC commit.

**Demo / interview acceptance**
- Release notes filed at `RELEASE-NOTES-v2.0.0-rc.md`.
- Five-minute interview narrative anchored to the RC build.

**Yellow-risk policy**
- No yellow risks may carry into the RC. Any remaining must be
  filed as v2.1 work.

---

## Gate Mechanics

| Mechanism | Owner | Where it lives |
|-----------|-------|----------------|
| Engineering acceptance | The PR opener | `pytest`, CI status, code review |
| Product acceptance | The reviewer | Demo recording + checked-in walk-through |
| Security acceptance | Designated reviewer with `security_reviewer` role | Security-acceptance checklist file under `examples/enterprise/demos/<stage>/security_check.md` |
| Evaluation acceptance | The PR opener | Eval CI lane + baseline diff |
| Demo / interview acceptance | The PR opener | Walk-through + screenshot in `examples/enterprise/demos/<stage>/` |

A stage may not be merged into a release branch unless all five
mechanism cells contain a green entry for that stage.

---

## What "Done" Does Not Mean

- "Done" does not mean polished UX. The CLI surface stays minimal
  until v1.9.4.
- "Done" does not mean live-provider validation. That is a separate
  lane and a separate gate, owned by the user, not the model.
- "Done" does not mean documentation is final. Docs may evolve;
  what is locked is the executable behavior described.
- "Done" does not mean the next stage is approved to start. The
  previous gate only confirms readiness, not prioritization.
