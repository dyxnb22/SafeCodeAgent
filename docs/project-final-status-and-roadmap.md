# SafeCode Agent Final Status and Roadmap

Status: current project baseline after `v4.9.3`.
Last updated: 2026-06-04.

This document is the consolidated product description for SafeCode Agent
through `v4.9.3`. The active forward plan now lives in
`docs/version-plans/v4.10-to-v4.12-resume-mvp-roadmap.md`, which covers the
DeepSeek provider, agentic-lite task loop, and resume-ready MVP cut. This
file remains the current entry point for what the project does and what it
does not yet do; the v4.10-v4.12 roadmap describes what should happen next.

## Current Product Shape

SafeCode Agent is a safety-first Python terminal coding agent and local agent
runtime. Its strongest shipped capability is an auditable local edit/run loop:

```text
collect context
-> propose patch
-> preview diff
-> human approval
-> checkpoint
-> apply patch
-> audit log
-> rollback
```

As of `v4.9.3`, the user-facing shape is shell-first:

```sh
cd /path/to/project
sac shell
```

From that shell, users can ask read-only questions, request project overview
context, propose edits, run configured project checks, inspect status, debug
the latest failure, apply an approved pending patch, and commit locally. The AI
shell is EXPERIMENTAL and intentionally keeps SafeCode's safety posture: no
auto-apply, no auto-commit, no push/PR automation, and no stable contract
promotion for v4.9 surfaces.

## Implemented Capabilities

### Stable Safety Runtime

- Config precedence and project-config lowering protection.
- Pending patch JSON format and diff preview.
- Checkpointed patch apply and rollback.
- Hash-chained audit log with anchor verification.
- Policy-gated command execution with high-risk command blocking.
- Sandbox proposal/approval/result lifecycle, with real backends still treated
  conservatively unless preflight and opt-in gates pass.
- Stable CLI JSON envelope and MCP read execution contracts from the v3.x/v4.0
  contract cuts.

### Agent and Coding Workflow

- `sac ask` for read-only project questions.
- `sac edit` for LLM-generated pending patch proposals.
- `sac apply` for explicit approval, checkpoint, file write, and audit.
- `sac rollback --last` for local recovery.
- `sac fix` and `sac fix --watch` for bounded test-fix proposal loops.
- `sac run` and `sac run --suite test|lint|typecheck|build` through policy.
- `sac commit` and `sac branch new` for local-only git delivery with dirty-tree
  guards.

### Task-First State

- `sac task` creates, lists, switches, shows, closes, and deletes local tasks.
- `sac status` summarizes current task state and next safe step.
- Task sidecars under `.sac/tasks/` bind edit/apply/run/fix/history activity to
  a current task.
- `sac resume` recovers interrupted or open work without auto-running commands.
- Per-task budgets and stuck-loop categories are recorded experimentally.

### Project Intelligence

- Project profile detection for test/lint/typecheck/build commands.
- Stack, entrypoint, test directory, git, docs, high-signal file, pinned memory,
  current task, and recent failure signals through `build_project_overview()`.
- Context collection, file indexing, Python symbol indexing, repo maps, and
  bounded context selection.
- Secret redaction and path/root boundary checks on display and context paths.

### Memory and Debugging

- Unified local memory under `.sac/memory/`, including project notes, pinned
  files, recent edits, recent failures, and task memory.
- `sac debug last-failure` for redacted latest failure summaries.
- `sac debug bundle` for redacted SafeCode metadata bundles without project
  source code.
- `sac audit query` for verified, read-only audit filtering.
- `sac smoke shell-first` and `sac smoke ai-shell` deterministic smoke suites.

### AI Shell MVP

- `sac shell` TTY and non-TTY REPL.
- Slash commands: `/status`, `/task`, `/overview`, `/apply`, `/commit`,
  `/debug`, `/help`, `/exit`.
- Natural-language router for ask/edit/fix/run/status/apply/commit/debug/
  overview/exit intents.
- Shell session state under `.sac/shell/` with fail-safe corrupt/future-version
  handling.
- Per-turn audit events and current-task binding.
- Write-class actions require explicit confirmation. Non-TTY mutation requests
  print direct CLI instructions instead of mutating.

## Can It Behave Like Claude Code?

Short answer: it can support a Claude Code-like local workflow at MVP level,
but it is not Claude Code parity.

What works today:

- `cd` into a project and run `sac shell`.
- Type natural-language prompts such as "what is this project?", "make the
  smallest safe fix", "run the tests", "apply the patch", and "commit this
  task".
- Get read-only answers through `ask` and structured `/overview` output.
- Generate pending patches through the existing edit/fix primitives.
- Run profile-based checks through policy.
- Apply and commit only after explicit confirmation.
- Preserve local state for status, resume, debug, audit, rollback, and memory.

Important boundaries:

- It does not autonomously keep working across many tool calls until the task is
  done.
- It does not auto-apply patches, auto-commit, push branches, or create PRs.
- It does not include RAG, embeddings, vector search, or LangGraph.
- It does not have a production IDE extension or full interactive TUI.
- Live-provider coding quality depends on the configured provider and is less
  proven than the mock-provider and deterministic safety paths.
- The v4.9 shell surfaces are EXPERIMENTAL and not stable automation contracts.

The honest product statement is: SafeCode Agent is a safety-first local coding
assistant with a coherent AI shell MVP. It is suitable for controlled local
patch workflows and security/agent-runtime demonstrations. It should not yet be
marketed as a full Claude Code replacement.

## Current Architecture

The architecture is intentionally layered:

1. **CLI and shell surface**: Typer commands plus `sac shell`.
2. **Task/session state**: `.sac/tasks/`, `.sac/shell/`, agent sessions, resume
   state, budgets, and progress.
3. **Context and memory**: collectors, redactors, selectors, repo maps, project
   profiles, pinned files, and recent failures.
4. **LLM orchestration**: ask/edit/fix flows, provider clients, patch parsing,
   diff planning, and structured tool intent routing.
5. **Safety gates**: patch validator, command policy, dirty-tree guard,
   sandbox planner/executor preflight, approvals, and hook gates.
6. **Evidence and recovery**: audit logs, runtime logs, traces, checkpoints,
   rollback, debug bundle, smoke/eval/reporting.

This structure is sound for a safety-first local agent. The main architectural
optimization now is not another orchestration framework; it is tighter reuse of
existing primitives inside the shell and fewer duplicate documentation pointers.

## Corrections Made In This Pass

- Fixed `sac shell /debug` to reuse `sac debug last-failure`'s real
  `find_last_failure()` implementation instead of importing a nonexistent
  module.
- Added regression coverage proving `/debug` reports last-failure evidence from
  the shell.
- Consolidated current docs and metadata around this status/roadmap file.
- Corrected current documentation claims that still described the completed
  v4.9 plan as active.
- Corrected the root visible command count after `sac shell` from 17 to 18 in
  current-facing docs.

## Forward Roadmap

### Phase 1: AI Shell Product Hardening

Goal: make the v4.9 shell feel coherent and reliable without weakening safety.

- Use project overview automatically as first-turn context for shell questions
  where appropriate.
- Add clearer shell responses for confirmation, pending patch location, diff
  review, and next safe step.
- Add more fixture-based shell journeys across Python, TypeScript, Go, and Rust.
- Keep non-TTY mutation behavior read-only/instructional.
- Keep all shell surfaces EXPERIMENTAL until broader evidence exists.

### Phase 2: Real Coding Quality and Provider Reliability

Goal: improve actual code-generation quality under live providers.

- Strengthen patch prompting and structured patch output validation.
- Improve retry, timeout, streaming, cost, and provider error reporting.
- Expand live-provider advisory smoke history without making it a required
  default for local users.
- Add stack-aware edit/fix examples that exercise real project structure.

### Phase 3: Context Engine Improvement

Goal: improve file selection and project understanding before considering RAG.

- Improve high-signal file ranking and symbol-aware context selection.
- Use profile, recent failures, pinned files, and task state more consistently
  in edit/fix prompts.
- Add budget explanations when files/signals are skipped.
- Defer embeddings/vector storage until structured local signals are exhausted.

### Phase 4: Loop Autonomy With Approval Boundaries

Goal: allow bounded multi-step work while preserving explicit approvals.

- Add a shell-level "plan then step" mode that can inspect, propose, run, and
  stop at approval boundaries.
- Reuse existing AgentLoop typed actions instead of adding a parallel loop.
- Require user approval before every write, command execution that needs it,
  apply, and commit.
- Store all loop state in existing task/session artifacts.

### Phase 5: Developer Experience Surfaces

Goal: improve daily usability after the terminal loop is reliable.

- Decide whether to mature the TUI or keep it frozen as experimental.
- Revisit the VS Code extension only after the shell loop is dependable.
- Improve install/update packaging evidence before public product claims.
- Keep push/PR automation out of scope until local commit flow is stronger.

### Phase 6: Contract Promotion Review

Goal: promote only surfaces with strong evidence.

- Keep v4.9 shell surfaces experimental for now.
- Re-run public-contract snapshot tests before any promotion.
- Promote only narrow contracts with stable schemas, repeatable smoke evidence,
  and documented threat-model implications.
- Do not schedule v5 solely because v4.9 shipped.

## Documentation Source Of Truth

- Current product status and plan: this file.
- Version matrix: `docs/version_implementation_matrix.md`.
- Public contracts: `docs/public-contracts.md`.
- Version semantics: `docs/versioning-policy.md`.
- User workflow guide: `docs/mvp-user-guide.md`.
- AI shell tutorial: `docs/tutorials/ai-shell-first-hour.md`.
- Commercial architecture reference:
  `docs/product-commercialization-roadmap.md`.

