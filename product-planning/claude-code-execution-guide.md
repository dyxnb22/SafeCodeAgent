# Claude Code / Codex Execution Guide

**Implementation status (v1.9):** Executable contracts through v1.9 are implemented; see `.agents/context/progress.json` for live stage state.
This file is the operating contract for any AI agent (Claude Code,
Codex, or similar) that picks up an implementation task on this
branch. It assumes you have already read `.claude/CLAUDE.md` and
the global Enterprise rules; this guide is the project-specific
addendum.

The most important rule:

> One sub-plan per PR. Keep it small. Keep it green. Update plans
> and decisions when reality diverges.

---

## How to choose the next task

1. Open `product-planning/version-roadmap.md` and confirm the
   current stage. The stage you are working on is the one whose
   acceptance gate in `milestone-acceptance.md` is *not yet
   green*.
2. Open `product-planning/execution-backlog.md` and find the
   lowest-id task in that stage whose dependencies are all merged.
3. If multiple tasks are unblocked, prefer ones that unlock the
   most downstream work (the dependency graph in
   `execution-backlog.md` is the guide).
4. If no task is unblocked, stop and ask the user — do not invent
   work.

Never start two tasks in parallel from the same conversation; the
backlog assumes serial execution per branch.

---

## Required reading before each task

Read these every time, in order. If a section is already in your
recent context, scan it; do not skip it.

1. `.claude/CLAUDE.md` and `.claude/rules/general-rules.md`.
2. `AGENTS.md`.
3. `product-planning/version-roadmap.md` (for the current
   stage and sub-plan).
4. `product-planning/execution-backlog.md` (for the specific task).
5. `product-planning/milestone-acceptance.md` (for the gate
   criteria this work contributes to).
6. The technical design document that anchors the task:
   - RAG work → `enterprise-docs/rag-implementation-plan.md` +
     `enterprise-docs/rag-and-context.md`.
   - Workflow work → `enterprise-docs/workflow-design.md` +
     `enterprise-docs/system-architecture-v1.md`.
   - Tool / MCP work → `enterprise-docs/mcp-and-tools.md` +
     `enterprise-docs/security-governance-plan.md`.
   - Governance / RBAC / approvals → `enterprise-docs/
     security-governance-plan.md` + `enterprise-docs/data-models.md`.
   - Trace / dashboard → `enterprise-docs/agentops-observability-plan.md`.
   - Eval → `enterprise-docs/evaluation-plan.md`.
7. The specific files listed under "Files/Modules" in the task.

---

## Sources you must NOT read for context

Reading is fine; *acting on* these is not. They are listed because
they have produced misdirected work in the past.

- The `archive/safecodeagent-final` branch.
- The `main` branch's `docs/` directory.
- The `CHANGELOG.md` for `v0.x.x` – `v5.x.x` release notes.
- The legacy `docs/version-plans/` content (already removed from
  this branch; if you find a copy elsewhere, do not import it).
- Demo walk-throughs from the original product (`docs/demo/`).
- Old version notes mentioning "ratchet promotion", "release
  train", or "stable contract tier".

If you find yourself wanting to reuse a concept from one of those
sources, copy the *idea* into the relevant enterprise doc with a
Decision entry; do not import the artifact.

---

## Confirming the scope of a task

Before writing any code:

1. Re-read the task entry in `execution-backlog.md`. Note the
   exact files, tests, and acceptance criteria.
2. Re-read the corresponding sub-plan in `version-roadmap.md`. The
   sub-plan defines the *what*; the backlog task defines the
   *how* for one PR.
3. List the files you intend to touch. They must be a subset of the
   task's `Files/Modules`. If you need a new file, add it to the
   task entry as part of the PR; do not silently create files.
4. List the tests you will add. They must match the
   `Tests` section.
5. Confirm dependencies are merged. If the task lists `Dependencies:
   v1.x.y-T<n>` and that PR is not merged, stop and switch tasks.
6. Confirm there is no overlap with a task currently in progress
   in another branch (`git branch -a` and `gh pr list`).

If the task's scope is unclear or contradicts another plan, **do
not silently widen the scope.** Add a Decision entry in
`decision-log.md` describing the conflict and the chosen resolution
in the same PR.

---

## How to write tests

- Add tests under the path listed in the task. If the path does not
  exist, create it.
- Use `pytest`; do not introduce other runners.
- Default LLM provider in tests is `mock`. Do not change this.
- Embedding backend in tests is the mock backend. Do not change
  this.
- Snapshot tests are encouraged for stable contracts (Pydantic
  models, action matrix entries, taxonomy). Keep snapshots in JSON
  or YAML, never embedded in code strings.
- A test that uses the network must be marked `@pytest.mark.live_provider`
  and is excluded from the default lane.
- A test that creates a file on disk uses `tmp_path`, not the repo.
- Property tests are welcome for invariants such as "approvals
  never double-consume"; keep them deterministic.

Each PR must include:

- New tests for new behavior.
- Updated tests when behavior changes.
- A passing `PYTHONPATH=src python3 -m pytest -q` run.
- For workflow-touching PRs, a passing run with `WORKFLOW_RUNTIME=
  langgraph` if the extras are installed (skip if extras absent;
  CI matrix handles this).

If the task says "no test in this PR" (rare; e.g. doc-only), make
sure a downstream task in the same stage adds the test, and link
to it in the PR description.

---

## How to update plan documents

When code lands, the plans must reflect reality.

1. **Mark the task done** in `execution-backlog.md` by adding a
   `Done in <commit-sha>` line under the task.
2. If you changed the scope (added or removed acceptance), edit
   the task entry and add a Decision entry to `decision-log.md`
   explaining why.
3. If the change affects a model or a contract in
   `enterprise-docs/data-models.md`, update the model section.
4. If the change adds an action to the matrix in
   `enterprise-docs/security-governance-plan.md`, update the
   matrix.
5. If the change touches a trace event type, update
   `enterprise-docs/agentops-observability-plan.md`.
6. If the change adds an eval case, register it under the suite in
   `enterprise-docs/evaluation-plan.md`.

Plan updates go in the *same* PR as the code change. They are not a
follow-up task.

---

## How to avoid over-design

Every enterprise PR has a temptation to refactor or generalize.
Resist it.

- Do not add abstractions beyond what the task requires.
- Do not add fallbacks for hypothetical providers.
- Do not add CLI commands that are not in the task.
- Do not add configuration options "for the future".
- Do not split a small task into a framework.
- Do not add comments that explain `what`; only `why`.
- Do not modify legacy modules under `src/safecode/` outside
  `enterprise/`. If you must, raise the change in a Decision entry
  *first* and split it into a separate PR.

If you find a real problem outside the task, file a backlog item
in `execution-backlog.md` and move on. Out-of-scope fixes pollute
the diff and slow review.

---

## How to handle blockers

You may stop and ask the user when:

- The task's scope conflicts with an entry in `decision-log.md`.
- A required file or fixture is missing and creating it changes
  the task's contract.
- A legacy module behaves unexpectedly and modifying it is the
  only way forward (always escalate; never quietly patch legacy).
- A network or provider call is required to complete a non-live
  test (this is always wrong; ask).
- A test refuses to fail locally but passes in CI or vice versa.
- The required dependency does not match the project's existing
  dependency list (e.g. a sub-package needs a new dependency not
  in `pyproject.toml`).

When you stop, leave the workspace clean. Do not partially commit;
do not leave a half-implemented module on disk that another agent
might find later and assume is complete.

---

## What approval / human action is required

Stop and request human approval (do not proceed) when:

- A PR would modify legacy `src/safecode/` files outside the
  `enterprise/` subdirectory.
- A PR would change `pyproject.toml` in a way that adds a hard
  dependency.
- A PR would touch `.claude/`, `AGENTS.md`, `README.md`,
  `SECURITY.md`, or `LICENSE`.
- A PR would modify policy-related YAML defaults in a way that
  weakens any tier.
- A PR would add a new public CLI command not listed in the task.
- A PR would update an eval baseline without `--update-baseline`
  reason.
- A PR would skip an existing test or mark it `xfail`.
- A PR would touch the audit chain logger or the sandbox
  primitives.
- A PR would introduce credentials or token-handling code paths.

For all of these, write a brief note in the PR description, link
the relevant Decision entry, and wait for human review before
merging.

---

## What to output at the end of a task

A PR must include, in this order:

1. **Summary** (one paragraph): what changed and why, referencing
   the sub-plan id.
2. **Files changed** list.
3. **Tests added/modified** list.
4. **Acceptance check** mapped to the task's acceptance criteria.
   Each criterion must be either ✓ with evidence (a test name) or
   ⨯ with explanation.
5. **Plan updates** list (every plan file touched).
6. **Decision updates** list (any `decision-log.md` entries
   added).
7. **Open follow-ups** list (any backlog items added).

If you used `TaskCreate`/`TaskUpdate` while implementing, leave
the task list in a clean state (no in-progress tasks for the
completed scope).

---

## Project-specific dos and don'ts

### Do
- Keep PRs under 1.5 days of work. Split if needed.
- Reuse legacy modules by composition.
- Run the full pytest suite before opening the PR.
- Add a snapshot for new contract surfaces.
- Use Pydantic v2.
- Use `Path` from `pathlib`; do not use string concatenation for
  paths.
- Use `argv` lists for subprocess; never shell strings.

### Don't
- Restore legacy docs.
- Add a database, queue, or external service.
- Add a web server, framework, or build pipeline for UI.
- Add a global mutable state holder.
- Add a "TODO: revisit later" comment without a backlog entry.
- Edit `src/safecode/` outside `enterprise/`.
- Edit the trace `redaction.py` to make a test pass.
- Introduce a `requests` or `httpx` direct call from workflow
  code; go through a connector.

---

## When the plan and code disagree

If your reading of the plan says X, but the code already does Y,
the plan is right unless reality forces otherwise. Two paths:

- **Code is the wrong implementation of an agreed plan** → fix
  the code to match the plan; add a regression test.
- **Plan is no longer correct** → update the plan in the same PR
  with a Decision entry; do not just align the plan to whatever
  the code happened to do.

Silent drift is the enemy. The Decision entry is the antidote.

---

## When the task description is ambiguous

Re-read the dependent design document and the related sub-plan.
If ambiguity remains:

- If the missing detail is a *contract* (field shape, decision
  matrix, schema), stop and ask.
- If the missing detail is a *style* choice (variable name,
  internal split), choose conservatively and move on.

If a contract appears underspecified, file a Decision entry
proposing the resolution. The PR can include both the Decision
and the implementation.

---

## What to do if you discover SafeCodeAgent legacy bugs

Treat legacy bugs as out of scope unless the bug blocks your
enterprise task. If it does:

1. Document the bug in the PR description.
2. File a backlog entry under a `legacy_followups` section in
   `execution-backlog.md`.
3. Add a Decision entry explaining the temporary workaround.
4. Patch the minimum needed in the legacy module; never restructure.
5. Get human approval before merging.

---

## End-of-task checklist (paste into PR description)

```
- [ ] Read the sub-plan and the related design doc(s).
- [ ] Listed files changed match the task's Files/Modules.
- [ ] Added/updated tests under the path in Tests.
- [ ] `PYTHONPATH=src python3 -m pytest -q` passes locally.
- [ ] Acceptance criteria all checked or explained.
- [ ] No legacy `src/safecode/` files outside `enterprise/`
  modified.
- [ ] No `.claude/`, `AGENTS.md`, `README.md`, `SECURITY.md`,
  `LICENSE` modified.
- [ ] Plan documents updated to reflect reality.
- [ ] Decision entries added if scope or interpretation changed.
- [ ] Backlog entries added for any out-of-scope follow-ups.
- [ ] Task IDs in `execution-backlog.md` marked Done with commit
  sha.
- [ ] PR description references the sub-plan id and acceptance
  criteria.
```

If a box cannot be ticked, explain why in the PR description
before requesting review. Reviewers will not merge a PR with an
unticked box and no explanation.

---

## Reference paths

- **Plans:** `product-planning/`
- **Designs:** `enterprise-docs/`
- **Source:** `src/safecode/enterprise/`
- **Tests:** `tests/enterprise/`
- **Examples / fixtures:** `examples/enterprise/`
- **Run artifacts (gitignored):** `.sac/enterprise/`
- **Branch:** `dev/enterprise-agent-platform`
- **Main branch (PR target unless noted):** check
  `version-roadmap.md` Stage gate; default to `main`.
