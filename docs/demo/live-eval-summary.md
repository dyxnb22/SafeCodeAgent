# Live Eval Results — DeepSeek v4 Flash

**Status:** Real provider artifact completed on 2026-06-17; default fixture
suite expanded after this artifact.
**Provider/model:** `deepseek` / `deepseek-v4-flash`.
**Credential handling:** API key was supplied only through the process
environment and is not stored in this artifact.

Command shape:

```bash
SAFECODE_LIVE_TESTS=1 \
SAFECODE_LLM_MODEL=deepseek-v4-flash \
sac eval --mode live --provider deepseek --model deepseek-v4-flash --fixture <fixture>
```

Recorded redacted snapshot summary:

```json
{
  "schema_version": 2,
  "provider": "deepseek",
  "model": "deepseek-v4-flash",
  "passed": "28/28",
  "artifact_fixture_count": 28,
  "current_default_fixture_count": 36,
  "total_wall_seconds": 205.6,
  "avg_wall_seconds": 7.3,
  "avg_tokens_per_fixture": 3045.1,
  "validation_commands_run": 8,
  "validation_commands_passed": true,
  "fixed_commit_inline_fixtures": 2,
  "terminal_style_fixtures": 2,
  "patch_retry_needed": false,
  "audit_chain_complete": true,
  "checkpoint_integrity_ok": true,
  "unauthorized_mutations": 0,
  "working_tree_clean_after_eval": true
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
- `AgentOrchestrator.edit()` now retries once after a patch validation failure,
  passing the validation error and exact current file contents back to the
  provider. This run did not need that path because all fixtures passed on the
  first proposal.
- The default live suite now includes 36 fixtures. The committed DeepSeek
  artifact above covers the earlier 28-fixture suite; the ratchet baseline now
  tracks the expanded 36-fixture default suite. Coverage includes
  validation commands, success-condition repair, relevant-file recall/precision,
  symbol localization, terminal-style tasks, and fixed-commit-inline real-project
  tasks.
- The ratchet baseline in `tests/snapshots/live_eval/baseline.json` has been
  promoted to the 28/28 DeepSeek run, so future stable-fixture failures are
  treated as regressions. Live provider runs remain opt-in and advisory.
- Targeted 2-run stability samples for the six newest fixtures all passed with
  `pass@1=1.000`, `pass@N=1.000`, and safety invariants OK.
