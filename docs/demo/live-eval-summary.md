# Live Eval Results — Placeholder

**Status:** Placeholder artifact (v5.6.1).

This file exists to satisfy the v5.6.1 roadmap requirement for a redacted
live eval result artifact. A real run requires `SAFECODE_LIVE_TESTS=1` and
an Anthropic or OpenAI API key:

```bash
SAFECODE_LIVE_TESTS=1 sac eval --mode live --provider anthropic
```

Results are written to `tests/snapshots/live_eval/latest.json`. After a
real run, copy the redacted output here.

---

## Expected Output Shape

```json
{
  "schema_version": 1,
  "results": [
    {
      "fixture_name": "python-add-function",
      "success": true,
      "turns_used": 3,
      "tool_calls": 5,
      "redundant_reads": 0,
      "input_tokens": 1450,
      "output_tokens": 310,
      "wall_seconds": 4.2,
      "error": null
    },
    {
      "fixture_name": "python-fix-failing-test",
      "success": true,
      "turns_used": 4,
      "tool_calls": 7,
      "redundant_reads": 0,
      "input_tokens": 2100,
      "output_tokens": 420,
      "wall_seconds": 6.8,
      "error": null
    }
  ]
}
```

## Architecture note

The live eval harness (`src/safecode/eval/live.py`) runs real coding tasks
against a live provider and collects:

- `success`: did the fixture's `success_condition` pass?
- `turns_used`: number of agent loop iterations
- `tool_calls`: total native tool calls
- `redundant_reads`: same file read twice (quality signal)
- `input_tokens` / `output_tokens`: from provider usage metadata
- `wall_seconds`: end-to-end latency

A ratchet baseline (`tests/snapshots/live_eval/baseline.json`) prevents
previously-passing fixtures from regressing. The CI `live-eval` job is
advisory (`continue-on-error: true`) and gated by `ENABLE_LIVE_LLM_TESTS`.
