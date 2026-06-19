---
name: SafeCodeAgent Enterprise Baseline
description: >
  Current branch context and task router for SafeCodeAgent Enterprise delivery.
---

# SafeCodeAgent Enterprise Baseline

Implemented. Git baseline: tag `v7.1.5`.

This branch extends the completed SafeCodeAgent safety kernel into a governed
enterprise security engineering agent platform.

## Mandatory Entry Context

Read these files before Enterprise implementation work:

1. `AGENTS.md`
2. `.agents/context/project-context.md`
3. `.agents/context/progress.json`

Use the task-to-context routing table in `project-context.md` to select only the
authoritative documents needed for the active task. Then inspect affected code,
callers, and tests. Do not treat the compact context as implementation truth.

## Product Goal

Build a governed secure-change platform for PR security review, vulnerability
remediation, secure implementation planning, compliance evidence, and auditable
tool use. The post-RC stages add a Team Server without weakening local mode.

## Reusable Safety Kernel

Preserve policy-gated writes and commands, checkpoint and rollback, hash-chain
audit, MCP proposal and approval, sandbox lifecycle gates, redacted approved
memory, context budgets, provider validation, and deterministic eval fixtures.

## Authoritative Delivery Planning

- `product-planning/version-roadmap.md`
- `product-planning/milestone-acceptance.md`
- `product-planning/execution-backlog.md`
- `product-planning/interview-master-narrative.md`
- `product-planning/decision-log.md`
- `product-planning/claude-code-execution-guide.md`
- `enterprise-docs/system-architecture-v1.md`
- `enterprise-docs/data-models.md`
- `enterprise-docs/workflow-design.md`
- `enterprise-docs/rag-implementation-plan.md`
- `enterprise-docs/security-governance-plan.md`
- `enterprise-docs/evaluation-plan.md`
- `enterprise-docs/agentops-observability-plan.md`
- `enterprise-docs/platform-architecture-v2.md` (normative for v2.1+)

Indexes: `product-planning/README.md` and `enterprise-docs/README.md`.

Foundation overviews are background only. Legacy product docs live on `main`
and `archive/safecodeagent-final`; do not recreate them here.

## Task Discipline

- Verify the active task and next task against `progress.json`.
- Read the exact backlog and acceptance entries before implementation.
- Apply the impact check from `project-context.md` before code changes.
- Update progress for every progress-bearing task using the protocol in
  `AGENTS.md`.
- Resolve context, plan, code, or test conflicts explicitly; never silently
  select the interpretation that is easiest to implement.
- For v2.1+ work, read the active stage section in
  `platform-architecture-v2.md` and preserve the explicit local/server backend
  boundary. Planned target-state prose is not evidence of implementation.
