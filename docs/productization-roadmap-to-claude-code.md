# SafeCode Agent Productization Roadmap to a Claude Code-like Runtime

## Current Readiness

SafeCode Agent is already useful as a safety-first local runtime for controlled
patches, command policy, audit, rollback, and policy-gated sandbox execution.
It is not yet a Claude Code-like product.

Practical readiness:

- Safety/runtime foundation: high. The project has diff review, checkpoint,
  rollback, command policy, network policy, audit anchoring, approval stores,
  sandbox planning, Noop policy-gated execution, and broad security tests.
- Local CLI usability: medium. Core commands exist and are testable, but the
  user still drives most steps manually.
- Autonomous coding-agent behavior: low to medium. `ask`, `edit`, `apply`,
  `run`, MCP, and subagents exist as separate commands, but there is no
  continuous agent loop that plans, chooses tools, observes failures, and asks
  for approval at the right time.
- Claude Code-like product experience: early. The runtime has many safety
  primitives, but lacks the interactive loop, polished context engine, tool
  orchestration, IDE/TUI surface, install/update flow, and large evaluation
  harness that make the product feel dependable in daily use.

Estimated distance:

- To a self-useable local coding assistant: about 2 major phases after v1.8
  (`v1.9` and `v2.0`).
- To a broadly usable Claude Code-like local product: about 6-8 major phases
  after v1.8 (`v1.9` through `v2.6`), depending on how much real OS sandboxing,
  IDE integration, and tool ecosystem depth is required.

## Biggest Gaps

1. Interactive agent loop
   The product needs one primary command that can hold a session, maintain a
   plan, choose safe tools, observe results, and continue until a user-visible
   goal is done.

2. Context quality
   The current context path is still mostly collector/index/selector based.
   A Claude Code-like experience needs better file ranking, symbol-aware
   context, test/build detection, and context budget management.

3. Real LLM operating mode
   There is an OpenAI-compatible client, but the runtime still needs robust
   prompt contracts, retries, response validation, model configuration UX, and
   graceful degradation.

4. Tool orchestration
   MCP, shell, sandbox, subagents, patch apply, and reports are available as
   separate capabilities. They need a shared tool-call protocol, permission
   prompts, result summaries, and replayable traces.

5. Product surface
   The CLI is functional, but a daily-use product needs an interactive command
   or TUI, clear approval prompts, progress display, IDE bridge, install/update
   story, and onboarding.

6. Real sandbox backends
   Noop execution is policy-gated and useful, but macOS Seatbelt, Linux
   Bubblewrap, and Docker are still dry-run only.

7. Evaluation and reliability
   The test suite is strong for security boundaries, but product reliability
   needs task-level evals: multi-file edits, failed tests, retry behavior,
   context misses, tool errors, and regression replay.

## Product Line

### v1.9.x: Interactive Agent Loop

Goal: turn separate commands into a coherent local agent session while keeping
all existing safety gates.

Subtasks:

- `v1.9.0-session-state`
  Persist `.sac/session.json` with current goal, plan, step index, pending
  action, and last observation.
- `v1.9.1-agent-step-command`
  Add `sac agent step "goal"` to run exactly one read/plan/tool-decision step.
- `v1.9.2-agent-run-loop`
  Add bounded `sac agent run "goal" --max-steps N` with approval stops.
- `v1.9.3-tool-intent-router`
  Introduce typed tool intents for read, patch, shell, sandbox, MCP, subagent,
  and report actions.
- `v1.9.4-human-checkpoint-prompts`
  Standardize approval prompts for patch apply, command execution, MCP write,
  and sandbox execute.
- `v1.9.5-agent-recovery`
  Persist failed step state and support `sac agent resume`, `abort`, and
  `explain-last-failure`.

Exit criteria:

- A user can run one goal through a visible plan without manually stitching
  together `ask`, `edit`, `run`, `apply`, and `sandbox` commands.
- Every write/execute action still passes through existing approval and audit
  paths.

### v2.0.x: Usable Local Coding Agent MVP

Goal: make SafeCode Agent useful for real small repository tasks end to end.

Subtasks:

- `v2.0.0-real-llm-agent-contract`
  Define structured LLM outputs for answer, plan, tool intent, patch proposal,
  and stop-for-user.
- `v2.0.1-context-budget-manager`
  Add ranked context packing with explicit token/byte budgets and source
  attribution.
- `v2.0.2-task-journal`
  Persist a human-readable task journal with plan, actions, diffs, commands,
  failures, and final summary.
- `v2.0.3-test-detect-and-run`
  Detect likely test commands and propose safe execution through policy gates.
- `v2.0.4-demo-workflow-suite`
  Add repeatable demo tasks for FastAPI, CLI, docs-only, and failing-test
  repair workflows.
- `v2.0.5-mvp-docs`
  Write install, model configuration, first task, safety model, and rollback
  docs.

Exit criteria:

- A new user can install, configure a model, run one realistic coding task,
  review the diff, run tests, apply, and rollback from documented steps.

### v2.1.x: Repository Intelligence

Goal: improve code understanding before adding more autonomy.

Subtasks:

- `v2.1.0-code-map`
  Build a lightweight repo map with files, symbols, imports, commands, tests,
  and entrypoints.
- `v2.1.1-test-build-detector`
  Detect pytest, uv, npm, pnpm, gradle, maven, go, cargo, and common lint
  commands.
- `v2.1.2-symbol-aware-context-selection`
  Rank context using symbol matches, imports, tests, recent failures, and
  user-mentioned paths.
- `v2.1.3-diff-planner`
  Add a planning phase that predicts touched files and validates final patch
  scope against the plan.
- `v2.1.4-context-debug-command`
  Add `sac context explain "task"` so users can see why files were selected.

### v2.2.x: Tool Ecosystem

Goal: make tool use safe, composable, and model-addressable.

Subtasks:

- `v2.2.0-tool-schema-registry`
  Define structured schemas for internal tools and their risk levels.
- `v2.2.1-model-tool-call-adapter`
  Convert LLM tool intents into runtime tool calls with validation.
- `v2.2.2-mcp-read-tool-loop`
  Let the agent call approved read-only MCP tools inside the bounded loop.
- `v2.2.3-mcp-write-review-flow`
  Connect MCP write proposals to the same review/apply/audit lifecycle.
- `v2.2.4-subagent-orchestration`
  Let the main agent spawn read-only subagents and merge their findings into
  one reviewed plan.

### v2.3.x: Developer Experience

Goal: make daily use feel like a product, not a bag of commands.

Subtasks:

- `v2.3.0-interactive-tui`
  Add an interactive terminal UI for plan, diff, approvals, command output, and
  history.
- `v2.3.1-config-wizard`
  Add `sac setup` for model provider, network policy, approval directories,
  and default safety preset.
- `v2.3.2-ide-bridge-mvp`
  Extend the IDE manifest into a minimal editor bridge for opening diffs and
  selected files.
- `v2.3.3-install-update-polish`
  Harden package metadata, version checks, doctor output, and upgrade docs.
- `v2.3.4-onboarding-examples`
  Provide guided examples for bug fix, feature edit, docs edit, and safe shell
  task.

### v2.4.x: Real Sandbox Backends

Goal: carefully enable real containment beyond Noop.

Subtasks:

- `v2.4.0-sandbox-backend-contract-v2`
  Split dry-run planning, preflight, and execution contracts per backend.
- `v2.4.1-macos-seatbelt-execution-preview`
  Enable an opt-in macOS Seatbelt execution path with narrow allowlists.
- `v2.4.2-linux-bubblewrap-execution-preview`
  Enable an opt-in Bubblewrap path with filesystem/network containment tests.
- `v2.4.3-docker-execution-preview`
  Enable opt-in Docker execution for isolated command runs.
- `v2.4.4-cross-backend-security-evals`
  Add backend-specific attack and escape evaluations.

### v2.5.x: Reliability and Evaluation

Goal: make quality measurable and regressions obvious.

Subtasks:

- `v2.5.0-task-eval-format`
  Define replayable task evals with repo fixture, user goal, expected outcome,
  and safety expectations.
- `v2.5.1-agent-replay-runner`
  Re-run saved sessions and compare actions, diffs, commands, and outcomes.
- `v2.5.2-failure-taxonomy`
  Classify context miss, patch parse failure, validation block, command block,
  test failure, model error, and user stop.
- `v2.5.3-quality-dashboard-report`
  Render local Markdown/HTML eval reports.
- `v2.5.4-performance-budgets`
  Track context size, command duration, LLM latency, and disk growth.

### v2.6.x: Product Hardening

Goal: make the product safe to hand to other developers.

Subtasks:

- `v2.6.0-policy-presets`
  Ship strict, balanced, and experimental safety presets.
- `v2.6.1-migration-system`
  Add migrations for `.sac` state and user-level approval/audit stores.
- `v2.6.2-release-signoff`
  Add release checklist automation for tests, docs, tags, and security evals.
- `v2.6.3-team-trust-boundaries`
  Document and enforce project/user/team trust boundary rules.
- `v2.6.4-product-security-review`
  Run a full security review over model prompts, tools, state, sandbox, and
  install/update paths.

## Recommended Next Move

Start with `v1.9.0-session-state`. It is the smallest useful bridge from a
safe command collection into an actual agent product. It also gives every
later feature a place to record plan, step, observation, failure, and resume
state.
