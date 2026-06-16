# SWE-bench Lite Eval Summary

**Status:** Harness complete. 3 synthetic tasks, mock provider baseline.
**Last run:** 2026-06-16

---

## What this is

SafeCode Agent v6.5.0 ships a **SWE-bench-Lite-compatible eval harness** — the
infrastructure to read SWE-bench-shaped tasks, run the agent on them, and record
structured pass/fail results. This is not a claim of SWE-bench score; it is the
scaffolding for reproducible, comparable coding-agent evaluation.

## Mock provider baseline (3 tasks)

| Instance | Passed | Failure reason |
|---|---|---|
| `safecode__calc-zero-div` | No | mock provider proposes no real patch |
| `safecode__config-missing-key` | No | mock provider proposes no real patch |
| `safecode__string-reverse` | No | mock provider proposes no real patch |

**Pass rate: 0/3 (mock baseline)**

This is expected and honest: the mock provider (`safecode.llm.mock.MockLLMClient`)
returns scripted responses for the existing test fixtures but does not generate real
patches for arbitrary bug-fix tasks. The 0% mock baseline confirms the harness is
measuring real agent capability, not test-rigging.

## How to run with a real provider

```bash
# Requires a live provider and network access
SAFECODE_LIVE_TESTS=1 sac eval --mode swebench-lite \
  --suite tests/eval_fixtures/swebench_lite \
  --provider deepseek \
  --limit 3
```

Results are saved to `tests/snapshots/swebench_lite/latest.json`.

## Task format

Each task is a JSON file in `tests/eval_fixtures/swebench_lite/`:

```json
{
  "schema_version": 1,
  "instance_id": "project__issue-42",
  "problem_statement": "The divide() function raises ZeroDivisionError...",
  "repo": {
    "kind": "inline",
    "files": {"calc.py": "def divide(a, b): return a / b"},
    "setup_commands": []
  },
  "test_command": "python -m pytest tests/ -q",
  "pass_condition": "exit_code_0",
  "hints": "Guard against b == 0."
}
```

This format is a subset of SWE-bench Lite's task structure. Fields map as:
- `problem_statement` → SWE-bench `problem_statement`
- `test_command` → derived from SWE-bench `FAIL_TO_PASS` test list
- `repo.files` → SWE-bench `base_commit` snapshot (simplified to inline)

## Architecture

```
sac eval --mode swebench-lite --suite <dir>
  → load_tasks_from_dir()
  → task_to_fixture()        # SWEBenchTask → TaskEvalFixture
  → TaskReplayRunner.run()   # existing replay infrastructure
  → SWEBenchRunner._replay_to_result()
  → SWEBenchReport
  → save_report() → tests/snapshots/swebench_lite/latest.json
```

The harness reuses all existing safety infrastructure: checkpoint, audit log,
approval gate, and filesystem boundary checks.

## Snapshot

`tests/snapshots/swebench_lite/latest.json` — committed mock-provider baseline.
Re-run with a real provider to update with actual results.
