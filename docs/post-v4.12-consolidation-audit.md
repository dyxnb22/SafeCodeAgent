# Post-v4.12 Consolidation Audit

Date: 2026-06-05
Baseline inspected: `main` at exact tag `v4.12.4` before this audit work.
Scope: architecture review, product/CLI review, documentation source-of-truth
review, and test/release hygiene review after the v4.10-v4.12 resume-ready MVP
train.

## Executive Summary

SafeCode Agent is in a good post-MVP shape: the v4.10-v4.12 train extended the
existing `AgentLoop`, kept the mutation gates intact, shipped a deterministic
FastAPI demo front door, and did not promote experimental surfaces to stable
contracts.

The main risk is now consolidation, not missing features. Agentic state is
spread across session state, typed journal events, task iterations, pending
patch files, runtime logs, and audit events. The pieces are individually small
and tested, but the boundaries are not yet documented tightly enough for another
feature train to build on confidently.

The biggest release hygiene issue is version semantics around `v4.12.4`: the
git tag exists at the inspected baseline and tracks the FastAPI todo project
profile, while package/runtime/lock metadata still report `4.12.3`. This should
be resolved before any push/release announcement that treats `v4.12.4` as a
package release.

Recommended direction: run a short v4.13 consolidation train before adding
hooks/skills or more autonomous orchestration.

## Current State After v4.12.4

- Initial git state matched the requested baseline: clean worktree, `HEAD` at
  exact tag `v4.12.4`, `main` ahead of `origin/main` by 19 commits.
- `v4.12.4` is a tracked-artifact hotfix commit:
  `fix(examples): track FastAPI todo project profile`.
- The README first viewport now points to the v4.12 mock demo:
  `examples/fastapi-todo/demo/run-demo.sh` and
  `docs/tutorials/from-task-to-tested-commit.md`.
- All v4.10-v4.12 provider, agentic, validation, resume, smoke, demo, and
  example surfaces remain EXPERIMENTAL.
- No `AgentTaskRunner` or parallel orchestration stack exists. The v4.11 work
  evolved `src/safecode/agent/loop.py`.

## Architecture Findings

1. `AgentLoop` is still the right center of gravity. `src/safecode/agent/loop.py`
   owns planning, tool routing, read-only MCP execution, subagent dispatch,
   patch proposal, approved MCP write execution, budgets, validation triggers,
   loop-stuck detection, and resume reconstruction. That is acceptable for the
   MVP, but it is now the main consolidation target.

2. Typed steps are projections over pending-action shape. `step_model.py`
   classifies from `pending_action["type"]`, `pending_action["route"]`, and
   `failure_category`. This is intentionally additive, but future changes to
   pending-action dictionaries can silently change typed event semantics.

3. Step index semantics need a single owner. Several paths classify with
   `step_index=saved.current_step` after incrementing `current_step`; validation
   also records synthetic `run` and `fix` events. This is testable today, but a
   future resume UI could misread whether indices are zero-based plan positions
   or one-based completed-step counters.

4. Validation has a split-brain boundary. `ValidationLoop` runs profile suites,
   journals typed `run`/`fix` results, appends task iterations, and may propose a
   repair patch through `AgentOrchestrator.edit()`. `AgentLoop` then maps the
   `ValidationLoopResult` back into session state. The split is thin and safe,
   but the state transition contract should be documented before extending it.

5. Agentic resume is useful but fragile. `AgentLoop.resume_from()` reconstructs
   state from journal events, but it derives waiting state from typed results
   rather than a canonical pending-action record. This is especially risky when
   a journal contains multiple historical `waiting_for_user` results.

6. CLI code owns some orchestration. `cli_resume.py` decides suggested next safe
   steps from pending patch state and typed result status; `cli_shell.py` has a
   separate `--agentic` rendering path over `AgentLoop.run()`. These are not
   broken, but the product now has several "continue the loop" surfaces.

7. Journal and audit remain separate, which is good, but cross-links are not
   centralized. Effectful boundaries may write audit events elsewhere, while
   `AgentJournalStore` records typed action/result events. A future report
   should not infer safety evidence from typed journal events alone.

8. Journal append uses atomic full-file rewrites. This is simple and safe for
   small MVP journals, but long sessions or future background execution would
   need either append-only writes with integrity checks or an explicit size cap.

## Product/CLI Findings

1. The first-user path is clearer than before v4.12. README now opens with the
   mock demo and links the transcript and tutorial before the command catalog.

2. The root CLI is appropriately conservative. Advanced surfaces such as
   `agent`, `demo`, `smoke`, `mcp`, `subagent`, `sandbox`, `api`, `tui`, and
   `report` remain hidden, while daily-loop commands remain visible.

3. There are overlapping entry points:
   `sac shell`, `sac shell --agentic`, `sac agent run`, `sac resume
   --continue-agent`, `sac demo agent-loop`, and `sac smoke agentic`. They serve
   different purposes, but the docs should name one recommended front door per
   audience.

4. The v4.12 demo is the right front door for now. It avoids credentials,
   network, IDE requirements, push/PR claims, and live-model quality claims.

5. Experimental labeling is mostly consistent. Public docs correctly state no
   auto-apply, no auto-commit, no RAG/embeddings, no LangGraph, no PR/push, and
   no stable-contract promotion for v4.10-v4.12.

6. Some docs are too long for first-run learning. `docs/mvp-user-guide.md`
   still carries many version-era sections. It is accurate, but it mixes a
   first-run path with implementation history.

## Documentation/Source-of-Truth Findings

Recommended ownership:

- Current product truth: `docs/project-final-status-and-roadmap.md`.
- Stable public contracts: `docs/public-contracts.md`.
- Implementation history: `docs/version_implementation_matrix.md` plus
  `docs/version-notes/`.
- Forward roadmap: `docs/version-plans/post-v4.12-consolidation-roadmap.md`.
- Architecture reference: `docs/product-commercialization-roadmap.md`.
- Historical productization context:
  `docs/productization-roadmap-to-claude-code.md`.

Findings:

1. `docs/project-final-status-and-roadmap.md` is the correct current product
   truth, but it still referenced `v4.12.3` as the current baseline before this
   audit. This audit updates that pointer to acknowledge the `v4.12.4` tracked
   profile hotfix.

2. `docs/version-plans/v4.10-to-v4.12-resume-mvp-roadmap.md` still described
   itself as an active forward plan. This audit marks it historical/completed.

3. `docs/version_implementation_matrix.md` remains the implementation-history
   ledger, but its "Current Project Status" section had not yet recorded the
   `v4.12.4` hotfix. This audit adds a row rather than changing runtime code.

4. `.claude/versions.json` had `current_implemented_tag` and `latest_tags`
   stale at `v4.12.3`. This audit syncs those git-tag pointers to `v4.12.4`.

5. `.claude/skills/current/SKILL.md` described the baseline as `v4.12.3`. This
   audit updates the baseline wording to `v4.12.4` while preserving the
   v4.12.3 package metadata history.

6. `docs/product-commercialization-roadmap.md` is still valuable as an
   architecture reference, but it should not be treated as the active roadmap.

7. `docs/productization-roadmap-to-claude-code.md` is useful historical context
   but now reads stale in places because it frames the current status at
   `v4.9.3`. Consolidate or mark it more aggressively historical later.

## Test/Release Hygiene Findings

1. P0: exact tag/package drift exists at the inspected baseline. `HEAD` was
   tagged `v4.12.4`, but `pyproject.toml`, `src/safecode/__init__.py`, and
   `uv.lock` still report `4.12.3`. Decide whether `v4.12.4` is a non-package
   tracked-artifact tag or run the proper release-bump and tag-move process
   before any release announcement.

2. `.claude/versions.json` stale-tag governance was expected to fail before
   this audit. This audit syncs the pointer to the latest git tag.

3. The tracked `examples/fastapi-todo/.sac/project_profile.json` is required by
   `tests/test_example_fastapi_todo.py` and by the documented deterministic
   validation command. `.gitignore` now has narrow exceptions for that file.

4. v4.10-v4.12 coverage is broad and local-first: DeepSeek preset and endpoint
   tests, provider doctor tests, live-provider refusal tests, typed agent/run
   tests, validation loop tests, agentic resume tests, agentic smoke tests,
   FastAPI example tests, demo transcript tests, and docs-claim guards.

5. Live provider tests remain opt-in and should stay advisory unless there is a
   dedicated credentials policy and CI lane decision.

6. The requested docs-only validation slice is appropriate for this audit
   because no runtime code is changed.

## Recommended Consolidation Plan

1. v4.13 should be a consolidation train, not a new feature train.
2. Write one short "agent state model" reference that maps session state,
   pending actions, typed journal events, task iterations, runtime logs, and
   audit events.
3. Clarify one product front door:
   - First-time user: v4.12 FastAPI mock demo.
   - Daily local loop: `sac task` + `sac status` + `sac edit/fix/apply`.
   - Experimental agentic path: `sac agent run`.
4. Add tests for resume reconstruction with multiple historical waiting states.
5. Add an architecture guard that prevents an `AgentTaskRunner` or parallel
   orchestration stack from being introduced accidentally.
6. Split only documentation/source boundaries first. Runtime refactors should
   wait until the state contract is documented.

## Prioritized Task List

### P0: Must Fix Before Push/Release Announcement

- Resolve the `v4.12.4` tag versus package/runtime/lock `4.12.3` mismatch.
- Ensure `.claude/versions.json` and `.claude/skills/current/SKILL.md` point to
  the intended current baseline.
- Keep `examples/fastapi-todo/.sac/project_profile.json` tracked; otherwise the
  demo/test profile is not clean-clone reproducible.

### P1: Should Fix Before Next Feature Train

- Document the canonical agent state model and ownership boundaries.
- Add resume reconstruction tests for journals with older and newer
  `waiting_for_user` typed results.
- Decide whether `sac shell --agentic` should exactly mirror `sac agent run`
  non-TTY failure behavior.
- Consolidate first-user docs so README and MVP guide have one primary path and
  the longer historical material moves behind references.
- Mark `docs/productization-roadmap-to-claude-code.md` explicitly historical at
  the top.

### P2: Good Cleanup

- Document typed step index semantics.
- Add a small table mapping each hidden/internal CLI surface to its intended
  audience.
- Add a note in public docs that typed journal events are not audit evidence by
  themselves.
- Consider a journal-size cap or compaction note before long-running sessions.
- Move duplicated agent-run rendering between `cli_agent.py` and
  `cli_shell.py` into a shared helper when behavior changes next.

### P3: Future Refactor/Roadmap

- Split `AgentLoop` only after the state model is documented and tested.
- Consider a canonical `AgentStateProjector` for session/journal/task/audit
  reads.
- Promote no v4.10-v4.12 surface to stable until a separate contract review.
- Revisit hooks/skills only after consolidation.
- Revisit real-provider demo hardening after package/tag semantics are clean.

## Do Not Do Now

- Do not introduce `AgentTaskRunner`.
- Do not introduce LangGraph or another orchestration runtime.
- Do not promote `sac agent run`, `sac shell --agentic`, validation, resume, or
  smoke to stable contracts.
- Do not add auto-apply, auto-commit, push, PR creation, background tasks, RAG,
  embeddings, or cloud execution.
- Do not do broad runtime refactors in this audit pass.
- Do not move or recreate release tags as part of documentation consolidation.

## Suggested Next Roadmap Direction

Choose `v4.13` as a consolidation train. A hooks/skills train should only start
after the state/source-of-truth cleanup above is complete and the tag/package
release semantics are resolved.
