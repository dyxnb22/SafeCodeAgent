# Eval Methodology

SafeCode uses four local eval lanes for product evidence: live coding fixtures,
a SWE-bench-Lite-compatible harness, a real-task slice, and a Markdown eval
dashboard.

## Live Eval Fixtures

A live fixture is representative when it exercises a behavior real coding
agents need in ordinary repositories:

- A small but failing local project state.
- A concrete user goal, not an implementation recipe.
- More than one possible edit path where possible.
- A success condition that can be checked locally by reading files or parsing
  Python AST, without network access.
- Coverage across different work types: calculator repair, docs edit,
  multi-file refactor, test failure repair, config schema migration,
  verification-required fixes, bounded repair, and context retrieval.

Live fixture results record more than binary pass/fail:

- Validation evidence: validation commands run, whether they passed, and how
  many commands were executed.
- Recovery evidence: whether a patch applied cleanly but the success condition
  failed, how many bounded repair attempts were used, and whether recovery
  succeeded.
- Retrieval evidence: relevant file recall, relevant file precision, and symbol
  localization accuracy for fixtures that declare expected context.
- Mergeability evidence: automated minimal-diff score, mergeability score, and
  reviewer-accept approximation for fixtures with declared expected files.
- Task provenance: inline, terminal-style, and fixed-commit-inline real-project
  fixtures are labeled separately so portfolio claims can distinguish synthetic
  regression tests from more realistic project tasks.
- Safety evidence: approval gates, audit-chain integrity, checkpoint integrity,
  unauthorized mutations, and leftover partial-patch artifacts.

The live lane is gated by `SAFECODE_LIVE_TESTS=1` because it can call a real
provider. Baselines are ratchets: once a fixture is recorded as passing, a
future failure is treated as a regression.

Repeated live runs can be summarized into pass@1, pass@N, pass rate, retry
rate, repair rate, recovery rate, average/p95 tokens, average/p95 wall time,
and whether safety invariants held for every run.

### v7.1 Eval Suites

Live fixtures are now filterable by suite:

- `regression`: stable tasks that should stay near 100% once passing.
- `capability`: harder or multi-turn tasks that should leave room for
  improvement.
- `safety`: scope, audit, checkpoint, and no-dangerous-tool behavior.
- `cost-perf`: reserved for token, wall-time, and tool-efficiency tasks.

Run a slice with:

```bash
sac eval --mode live --eval-suite capability --provider deepseek
```

Transcript artifacts are opt-in:

```bash
sac eval --mode live --eval-suite capability --transcripts --provider deepseek
```

When enabled, SafeCode writes redacted JSON transcripts under
`.sac/eval/transcripts/`. These artifacts record fixture metadata, the user
goal, validation commands, trajectory milestones, and the final outcome.

Each live result also serializes deterministic grader outcomes for fixture
outcome, validation, safety invariants, scope control, and reviewer-gate
quality. These grader records feed reports without replacing the fixture
success condition.

## SWE-bench Lite Compatibility

The `swebench-lite` mode implements a compatibility layer for
SWE-bench-Lite-shaped task JSON: `instance_id`, problem statement, repo
description, test command, and pass condition. This lets SafeCode exercise the
same harness shape used by larger benchmark workflows.

The fixtures in `tests/eval_fixtures/swebench_lite/` are still synthetic inline
fixtures. They do not claim to be official SWE-bench Lite instances, and they
do not require external repositories or Python packages beyond pytest.

## Real-Task Slice

`sac eval --mode real-task` selects SWE-bench-Lite-compatible tasks whose
`instance_id` does not start with `safecode__`. This separates external-project
issue adaptations, such as `arrow__parser-error-boundary`, from local synthetic
micro-fixtures while reusing the same replay and reporting path.

## Eval Dashboard

`sac eval --mode dashboard` reads the latest live, SWE-bench Lite, and real-task
JSON reports and writes a Markdown dashboard to `.sac/eval/dashboard.md` by
default. It reports missing sources, per-suite pass rates, aggregate pass rate,
and compact failure lines.

## Running With A Real Provider

Mock provider runs are deterministic and suitable for CI:

```bash
sac eval --mode swebench-lite --suite tests/eval_fixtures/swebench_lite
```

To run against a live provider:

```bash
SAFECODE_LIVE_TESTS=1 sac eval --mode swebench-lite --suite tests/eval_fixtures/swebench_lite --provider deepseek
```

## Current Benchmark Statement

The current committed SWE-bench Lite snapshot is an honest mock-provider
baseline over seven synthetic inline fixtures plus one real-world inline
adaptation. A `0/8` mock score is expected:
it proves the harness can run and report failures, not that the mock provider
can solve coding tasks. Real-provider results should be recorded separately
with provider, model, date, and environment details.
