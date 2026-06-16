# Live Eval Results — DeepSeek v4 Flash

**Status:** Real provider run completed on 2026-06-16.
**Provider/model:** `deepseek` / `deepseek-v4-flash`.
**Credential handling:** API key was supplied only through the process
environment and is not stored in this artifact.

Command shape:

```bash
SAFECODE_LIVE_TESTS=1 \
SAFECODE_LLM_MODEL=deepseek-v4-flash \
sac eval --mode live --provider deepseek --model deepseek-v4-flash --fixture <fixture>
```

Recorded redacted snapshot:

```json
{
  "schema_version": 1,
  "results": [
    {
      "fixture_name": "python-add-function",
      "success": true,
      "turns_used": 1,
      "tool_calls": 1,
      "redundant_reads": 0,
      "input_tokens": 0,
      "output_tokens": 0,
      "wall_seconds": 9.706,
      "error": null
    },
    {
      "fixture_name": "python-fix-failing-test",
      "success": true,
      "turns_used": 1,
      "tool_calls": 1,
      "redundant_reads": 0,
      "input_tokens": 0,
      "output_tokens": 0,
      "wall_seconds": 3.871,
      "error": null
    }
  ]
}
```

The machine-readable copy lives at
`tests/snapshots/live_eval/latest.json`.

## Notes

- The live eval harness now performs the full proposal -> apply -> success
  condition loop in a temporary workspace.
- Live eval explicitly enables network only for the selected provider host.
  For DeepSeek, the allowlist is `api.deepseek.com`.
- Provider patch generation uses the same JSON contract validator as other
  structured agent responses, then extracts the SafeCode SEARCH/REPLACE patch
  envelope before parser validation.
- The ratchet baseline remains in `tests/snapshots/live_eval/baseline.json`;
  live provider runs are opt-in and advisory.
