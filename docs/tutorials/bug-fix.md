# Bug Fix Tutorial

Materialize:

```bash
sac demo materialize failing-test-repair
cd examples/demo-workflows/failing-test-repair
```

Run the failing test, ask SafeCode for the repair, apply after reviewing the diff, then rerun tests:

```bash
sac test run --yes
sac edit "Fix the calculator add function so the existing failing test passes."
sac apply
sac test run --yes
```
