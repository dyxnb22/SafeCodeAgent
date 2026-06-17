# Post-v4.12 Consolidation Roadmap

Status: historical planning record. Consolidation/provider-profile planning was
carried through `v4.14.0`; active forward usability work now lives in
`docs/version-plans/post-v4.14-usability-roadmap.md`.
Baseline: `v4.12.4` tracked-profile hotfix on top of the `v4.12.3` resume-MVP
package metadata.

## Goal

Make SafeCode Agent easier to extend after the resume-MVP cut by consolidating
state ownership, docs source-of-truth, CLI guidance, and release metadata
before adding new product features.

This roadmap is intentionally not a hooks/skills feature train.

## Non-Goals

- No `AgentTaskRunner`.
- No parallel orchestration stack.
- No stable-contract promotion.
- No auto-apply, auto-commit, push, PR, background, RAG, embeddings, LangGraph,
  or cloud task behavior.
- No broad runtime refactor before the state model is documented and tested.

## Milestones

### v4.13.0 - State Model Consolidation

- Document the canonical relationship between:
  `AgentSessionState`, pending actions, typed journal events, task iterations,
  runtime logs, audit events, and pending patch/proposal files.
- Add focused tests for agentic resume with multiple historical
  `waiting_for_user` typed results.
- Add an architecture guard that the v4.11+ loop continues to evolve
  `AgentLoop` rather than introducing `AgentTaskRunner`.

Validation:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_resume_agentic.py tests/test_agent_journal_typed_events.py tests/test_cli_agent_run.py
```

### v4.13.1 - Product Surface Consolidation

- Name one recommended front door per audience:
  - first-time demo: FastAPI todo mock transcript;
  - daily loop: task/status/edit/fix/apply;
  - experimental agentic loop: `sac agent run`.
- Keep hidden/internal commands documented only in advanced or troubleshooting
  sections.
- Make `sac shell --agentic` and `sac agent run` output/failure semantics
  intentionally aligned or intentionally differentiated.

Validation:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_docs_claims_guard.py tests/test_cli_agent_run.py tests/test_cli_shell.py
```

### v4.13.2 - Docs and Release Truth Consolidation

- Keep `docs/project-final-status-and-roadmap.md` as current product truth.
- Keep `docs/version_implementation_matrix.md` and `docs/version-notes/` as
  implementation history.
- Mark old roadmaps historical where their opening sections still look active.
- Resolve the `v4.12.4` tag/package metadata decision before announcing any
  release based on that tag.

Validation:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_docs_claims_guard.py tests/test_versions_json_sync.py tests/test_versioning_policy_doc.py
```

### v4.14.0 - Provider Profile UX

Status: implemented in `v4.14.0`.

Context: the current `sac model <model> --provider <provider> --api-key ...`
surface technically works, but it makes the user think in raw config fields.
That is the wrong mental model. A daily user should configure a provider account
once, then switch among that provider's models with short names.

Comparable product cues:

- Claude Code starts an interactive session with bare `claude`, supports
  `--model` as a one-session override, and documents `/model` as the mid-session
  model switcher that can persist the default for new sessions.
- Claude Code's `/config` settings UI adjusts model and preferences, while
  hierarchical settings keep user, project, and local concerns separate.
- DeepSeek's Reasonix integration configures the DeepSeek API key on first run,
  persists it under `~/.reasonix/config.json`, defaults daily work to Flash, and
  exposes quick Pro escalation (`/pro`, `/preset max`) instead of asking users
  to re-enter base URLs or API keys.

Desired user experience:

```bash
sac provider add deepseek
# prompts once for API key; writes trusted user config

sac model flash
sac model pro
sac --model deepseek:pro "review this diff"

sac
sac> /model
sac> /model pro
sac> /provider status
```

Required changes:

- Add a user-level provider profile store:
  `~/.safecode/providers.toml` or a `[providers.<name>]` table in the existing
  user config. A provider profile owns `base_url`, credential reference or
  encrypted/plain local key storage policy, default model, model aliases,
  network host allowlist, and optional fallback model.
- Keep project config focused on safety and project policy. A project may
  recommend or pin a provider/model alias, but cannot introduce credentials or
  silently weaken user-level safety/network policy.
- Add first-class commands:
  - `sac provider add deepseek`
  - `sac provider list`
  - `sac provider status`
  - `sac provider use deepseek`
  - `sac provider rm deepseek`
  - `sac model list`
  - `sac model use flash|pro|deepseek-v4-flash|deepseek-v4-pro`
- Make `sac model` without arguments open an interactive picker in TTY mode and
  print current effective config in non-TTY mode.
- Support one-shot overrides with `sac --model <alias-or-id>` and
  `sac shell --model <alias-or-id>` without persisting.
- Teach shell `/model` the same semantics:
  - no argument: picker / current status;
  - alias argument: switch current session and optionally persist;
  - explicit `--save` persists as the user default;
  - output always states whether the change is session-only or saved.
- Add DeepSeek built-in aliases:
  - `flash` -> `deepseek-v4-flash`
  - `pro` -> `deepseek-v4-pro`
  - provider-scoped names also accepted: `deepseek:flash`, `deepseek:pro`.
- Add provider-specific setup defaults:
  - DeepSeek owns `base_url = "https://api.deepseek.com"`;
  - DeepSeek owns `network_allowlist = ["api.deepseek.com"]`;
  - user no longer types `base_url` or `network_allowlist` for the common path.
- Add a migration from the v4.13-era `[llm] api_key/provider/model/base_url`
  user config into provider profiles. Migration must create a backup and redact
  secrets from logs.
- Update `sac doctor` with a provider UX section:
  effective provider, effective model alias + model id, credential source
  (env/user config/keychain later), user network policy, project network policy,
  and next command to fix any missing piece.
- Keep env vars as power-user overrides:
  provider-specific key env vars and `SAFECODE_LLM_*` remain higher priority
  than persisted profiles.

Validation:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_provider_profiles.py tests/test_cli_model_config.py tests/test_provider_doctor.py tests/test_cli_shell.py
```

Exit criteria:

- A new DeepSeek user can reach a working session with one setup command plus
  one confirmation/prompted key entry.
- Switching from Flash to Pro never requires retyping provider, base URL, API
  key, or network allowlist.
- The CLI always explains whether a model change is persisted or session-only.
- Existing `SAFECODE_LLM_*` and provider key environment variables still work.
- No project-local file can store a credential or silently widen network policy.

### v4.14.1 - Interactive Config and Status Surfaces

Status: superseded by the more specific post-v4.14 usability plan. See
`docs/version-plans/post-v4.14-usability-roadmap.md`.

- Add `/config` as the in-shell settings hub. It should expose model/provider,
  safety mode, network status, shell approval mode, and display preferences.
- Add `/status` or `/provider status` output that is useful before a first
  prompt: provider, model, current task, network readiness, and credential
  source with secrets redacted.
- Add command suggestions for common missteps:
  - user tries `deepseek-v4-falsh` -> suggest `deepseek-v4-flash`;
  - user runs a real provider with missing project network -> print the exact
    `sac setup --yes --network` or provider-profile command;
  - user configures only project `[llm]` -> explain that provider selection is
    user-level.
- Add docs that teach the mental model first:
  "Provider account first, model switch second, project safety third."

Validation:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_cli_shell.py tests/test_provider_doctor.py tests/test_docs_claims_guard.py
```

## Exit Criteria

- A contributor can tell which document is current product truth, history, and
  forward roadmap in under two minutes.
- A contributor can tell which component owns each agent state transition.
- Resume behavior is protected against stale historical typed results.
- Release metadata and tag semantics are internally consistent.
- No experimental v4.10-v4.12 surface is accidentally described as stable.
- Provider/model configuration has a provider-profile UX plan with testable
  milestones and no credential writes to project-local config.
