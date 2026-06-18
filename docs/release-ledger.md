# SafeCode Release Ledger

This is the compact human-facing release ledger. It replaces the old
release-by-release reading path under `docs/version-notes/`.

Release tooling reads this file by `## vX.Y.Z` headings. Keep one concise entry
per release that matters for changelog, metadata, and release guard checks.
Detailed implementation archaeology belongs in git history and
[version_implementation_matrix.md](version_implementation_matrix.md).

## v7.1.5 - Eval Report Dashboard

Eval report dashboard summarizes latest live, SWE-bench Lite, and real-task JSON
reports into Markdown at `.sac/eval/dashboard.md`.

## v7.1.4 - Real-Task Benchmark

Real-task benchmark lane selects external-project SWE-bench-Lite-compatible
tasks, renders benchmark provenance, and saves `.sac/eval/real-task/latest.json`.

## v7.1.3 - Balanced Negative Evals

Default live suite expanded to 38 fixtures with safety cases for simple fixes
and docs-only repairs without code churn.

## v7.1.2 - Multi-Grader Schema

Live eval results now include structured grader outcomes for fixture outcome,
validation, safety invariants, scope control, and reviewer-gate quality.

## v7.1.1 - Live Eval Transcript Artifacts

Opt-in redacted live eval transcripts record fixture metadata, trajectory
milestones, validation commands, and outcome metrics.

## v7.1.0 - Eval Suite Split

Live fixtures are classifiable and filterable as regression, capability, safety,
or cost-performance slices.

## v7.0.4 - Session and Shell Polish

Adds session timeline projection, `sac session show --timeline`, shell timeline
commands, and resume quality improvements.

## v7.0.3 - Productized Subagent Roles

Adds productized read-only subagent roles for explore, review, and scout flows.

## v7.0.2 - Single-Command Agent Run

Improves `sac agent run` with `--auto-edit`, `--full-auto`, `--tests`, and richer
human/JSON summaries.

## v7.0.1 - Metadata and Narrative Sync

Synchronizes package metadata, README narrative, documentation index, and the
v7.0.x productization follow-up plan.

## v7.0.0 - Second Stable Contract Cut

Second stable-contract cut with 23 stable contracts and no v6.0 breaking
changes.

## v6.1.0 - Portfolio Maturity

Adds real DeepSeek eval evidence, realistic demo material, hook stages, and
diagnostics-aware context collection.

## v6.0.0 - Major Contract Cut

Promotes trust mode schema and session rollback while preserving v5.0 contracts.

## v5.8.2 - v6 Preparation Baseline

Completes the v5.6-v5.8 agent quality, security, cost, and v6-prep trains.

## v5.0.0 - First Stable Native-Tool Contract

Promotes native tool schemas, native-tool audit event types, checkpoint rollback,
and command policy contracts.

## v4.25.2 - Hardening Docs

Documents checkpoint integrity, `.sac/` writability, low disk space, and provider
connectivity hardening.

## v4.18.2 - Rollback Safety Regression Fix

Fixes rollback safety behavior while preserving approval, checkpoint, and audit
invariants.

## v4.12.4 - FastAPI Todo Profile Tracking

Adds tracked FastAPI todo demo project profile evidence.

## v4.0.0 - Contract Cut

Contract cut with zero breaking changes to the v3.0 public contract surface.

## v3.10.1 - CI Gates and Live Provider Lane

Records advisory loop-eval and live-provider CI lane status without requiring
secrets for ordinary regression runs.

## v3.0.0 - Public Contract Stabilization

Stabilizes the public local safety runtime contract direction.

## v2.6.21 - v2.6 Final Signoff

Final v2.6 signoff after release tooling, docs guard, metadata, and policy audit
work.

## v2.6.15 - Release Changelog Generator

Adds `sac release changelog` for Markdown changelog previews.

## v2.6.9 - Release Docs Guard

Adds docs finalization checks for release readiness.

## v2.6.8 - Release Metadata Index

Adds release metadata auditing for package/runtime versions, git tag, release
entries, and baseline consistency.

## v2.0.0 - Real LLM Agent Contract

Establishes the real LLM agent contract after the early local-agent MVP.

## v1.8.0 - Local Policy-Gated Execution MVP

Introduces local policy-gated execution as the first major safety runtime track.

## v0.1.0 - Ask and Audit

Initial ask/audit proof of concept.
