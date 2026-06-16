# Eval Methodology

SafeCode uses two local eval lanes for product evidence: live coding fixtures
and a SWE-bench-Lite-compatible harness.

## Live Eval Fixtures

A live fixture is representative when it exercises a behavior real coding
agents need in ordinary repositories:

- A small but failing local project state.
- A concrete user goal, not an implementation recipe.
- More than one possible edit path where possible.
- A success condition that can be checked locally by reading files or parsing
  Python AST, without network access.
- Coverage across different work types: calculator repair, docs edit,
  multi-file refactor, test failure repair, and config schema migration.

The live lane is gated by `SAFECODE_LIVE_TESTS=1` because it can call a real
provider. Baselines are ratchets: once a fixture is recorded as passing, a
future failure is treated as a regression.

## SWE-bench Lite Compatibility

The `swebench-lite` mode implements a compatibility layer for
SWE-bench-Lite-shaped task JSON: `instance_id`, problem statement, repo
description, test command, and pass condition. This lets SafeCode exercise the
same harness shape used by larger benchmark workflows.

The fixtures in `tests/eval_fixtures/swebench_lite/` are still synthetic inline
fixtures. They do not claim to be official SWE-bench Lite instances, and they
do not require external repositories or Python packages beyond pytest.

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
