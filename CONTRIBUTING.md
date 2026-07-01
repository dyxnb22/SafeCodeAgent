# Contributing

SafeCodeAgent Enterprise is feature-frozen. Contributions should focus on
correctness, security, compatibility, documentation, and reproducibility—not
new product scope unless explicitly approved.

## Setup

```bash
git clone <repo>
cd SafeCodeAgent-enterprise-agent-platform
uv sync --extra enterprise
uv run sac doctor
```

## Working Rules

- Read `AGENTS.md` and the routed context before editing.
- Preserve policy gates, approvals, audit, redaction, checkpoint, rollback,
  tenant isolation, and deny-by-default behavior.
- Keep changes narrowly scoped; do not mix refactors or dependency upgrades.
- Use typed models and structured parsing at trust boundaries.
- Never enable live providers or network access in deterministic tests.
- Do not commit generated state, credentials, caches, coverage, or test output.

## Verification

Run the closest tests first, then broaden according to risk:

```bash
# Narrow example
uv run --extra enterprise python -m pytest -q tests/enterprise/<domain>

# Enterprise regression
uv run --extra enterprise python -m pytest -q tests/enterprise

# Full regression for shared or security-sensitive behavior
uv run --extra enterprise python -m pytest -q
```

Behavior changes require positive and negative tests. Snapshot changes must be
intentional and reviewed as public contract changes.

## Native Tools and Providers

Changes to a native tool must preserve its `NativeToolSpec`, dispatcher
registration, policy category, audit event, redaction, and negative tests.
Unknown or newly write-capable tools remain denied until explicitly classified.

Changes to an LLM provider must preserve the `LLMClient` protocol and factory
routing. Tests use the mock provider by default; live-provider checks remain
opt-in and must never be required for deterministic CI.

## Documentation

- Update maintained contracts only when behavior or decisions change.
- Keep release status honest: portfolio readiness is not Enterprise GA.
- Add an architectural decision to `product-planning/decision-log.md` when a
  settled boundary changes.
- Do not recreate historical roadmaps, worklogs, or per-task evidence reports.

## Commit Message Style

Use a focused message such as:

```text
fix(approval): preserve tenant binding on replay
docs(architecture): clarify worker trust boundary
```

Explain why the change is needed and keep each commit independently testable.
