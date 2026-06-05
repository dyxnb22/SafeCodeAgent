# Post-v4.12 Consolidation Roadmap

Status: proposed consolidation plan after the v4.10-v4.12 resume-ready MVP
train.
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

## Exit Criteria

- A contributor can tell which document is current product truth, history, and
  forward roadmap in under two minutes.
- A contributor can tell which component owns each agent state transition.
- Resume behavior is protected against stale historical typed results.
- Release metadata and tag semantics are internally consistent.
- No experimental v4.10-v4.12 surface is accidentally described as stable.
