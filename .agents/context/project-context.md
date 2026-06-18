# SafeCodeAgent Enterprise Project Context

<!-- project-context:v1 -->

This is the compact navigation layer for agents. It summarizes stable project
facts and routes tasks to authoritative documents. It does not replace those
documents or the code. When this summary and an authoritative source disagree,
the authoritative source wins and this file must be corrected.

## Product And Current State

SafeCodeAgent Enterprise extends the completed SafeCodeAgent safety kernel into
a governed enterprise security engineering agent platform. Target workflows are
PR security review, vulnerability remediation, secure implementation planning,
compliance evidence, and auditable tool-using security operations.

- Legacy implemented baseline: `v7.1.5`.
- Enterprise planning and namespace stages: complete.
- Current delivery stage: `v1.5 AgentOps Observability and Trace Dashboard`.
- Next delivery task: `v1.5.1-T2 Wire emitter into workflow nodes and approval engine`.
- Machine-readable live status: `.agents/context/progress.json`.

Do not infer current progress from prose in this file. Read `progress.json`.

## Source Precedence

Use sources in this order for Enterprise delivery work:

1. Security invariants and working rules in `AGENTS.md`.
2. Live task state in `.agents/context/progress.json`.
3. Accepted decisions in `product-planning/decision-log.md`.
4. Milestone scope and acceptance in `product-planning/version-roadmap.md` and
   `product-planning/milestone-acceptance.md`.
5. PR-sized task contracts in `product-planning/execution-backlog.md`.
6. Domain design in the relevant `enterprise-docs/` plan.
7. Current code and durable tests for implemented behavior.
8. Foundation overview documents for background only.

Code is evidence of current behavior, not authority to weaken an accepted
security contract. If sources disagree, report and resolve the conflict before
implementing the affected behavior.

## Architecture At A Glance

The target architecture has these dependency layers:

1. Interface: CLI first; JSON contracts remain independent of future UI.
2. Workflow: deterministic local orchestration with optional LangGraph adapter.
3. Agent nodes: typed inputs and outputs; model results remain proposals.
4. RAG: permission-aware sources, chunks, hybrid retrieval, and citations.
5. Tool and MCP: locally classified capabilities behind governance checks.
6. Governance: policy precedence, RBAC, approval tiers, and grant validation.
7. Observability: redacted traces, timelines, cost, and approval visibility.
8. Evaluation: deterministic suites and regression ratchets.
9. Audit: append-only hash-chain evidence across governed actions.

Control flows downward through typed contracts. Tool execution does not bypass
governance. Audit, redaction, approval, checkpoint, and rollback are cross-layer
requirements rather than optional adapters.

Authoritative architecture: `enterprise-docs/system-architecture-v1.md`.
Authoritative models: `enterprise-docs/data-models.md`.

## Reusable Kernel Boundaries

| Area | Existing module | Enterprise use |
|---|---|---|
| Agent/tool lifecycle | `src/safecode/agent/`, `src/safecode/tools/` | Compose behind typed Enterprise nodes |
| Policy | `src/safecode/policy/` | Preserve no-weakening behavior |
| Audit | `src/safecode/audit/` | Extend event taxonomy; keep hash chain |
| Checkpoint/rollback | `src/safecode/checkpoint/` | Reuse for write workflows |
| Context/index | `src/safecode/context/`, `src/safecode/index/` | Reuse primitives behind permission-aware RAG |
| MCP | `src/safecode/mcp/` | Wrap with local classification and approval |
| Memory | `src/safecode/memory/` | Store only redacted, approved facts |
| Sandbox | `src/safecode/sandbox/` | Gate scanner and command execution |
| Evaluation | `src/safecode/eval/` | Extend with Enterprise suites |
| Enterprise surface | `src/safecode/enterprise/` | New schemas, RAG, workflows, connectors, governance |

Do not modify the reusable kernel when composition from `safecode.enterprise`
can satisfy the contract. Kernel changes require explicit compatibility and
regression analysis.

## Feature And Stage Map

| Stage | Capability | Status | Primary design |
|---|---|---|---|
| v1.0 | Enterprise branch, plans, namespace | Complete | `product-planning/` |
| v1.1 | Permission-aware RAG knowledge base | Complete | `enterprise-docs/rag-implementation-plan.md` |
| v1.2 | Typed workflow state and orchestration | Complete | `enterprise-docs/workflow-design.md` |
| v1.3 | Native, connector, scanner, and MCP layer | Complete | `enterprise-docs/system-architecture-v1.md` |
| v1.4 | Policy, RBAC, approval, and audit governance | Complete | `enterprise-docs/security-governance-plan.md` |
| v1.5 | AgentOps trace and dashboard | Ready | `enterprise-docs/agentops-observability-plan.md` |
| v1.6 | Evaluation and regression platform | Planned | `enterprise-docs/evaluation-plan.md` |
| v1.7 | PR security review workflow | Planned | `enterprise-docs/workflow-design.md` |
| v1.8 | Vulnerability remediation workflow | Planned | `enterprise-docs/workflow-design.md` |
| v1.9 | Enterprise beta hardening | Planned | `product-planning/version-roadmap.md` |
| v2.0 | Enterprise release candidate | Planned | `product-planning/version-roadmap.md` |

Status details belong in `progress.json`; change this table only when stage
scope, ownership, or architecture changes.

## Task-To-Context Routing

Read only the row needed for the active task, plus directly affected code and
tests.

| Task type | Required authoritative context |
|---|---|
| Prioritization or scope | version roadmap, milestone acceptance, execution backlog, decision log |
| RAG or citations | RAG implementation, data models, security governance, evaluation plan |
| Workflow or state | workflow design, data models, system architecture, security governance |
| Connectors, tools, scanners, MCP | system architecture, security governance, workflow design, data models |
| Policy, RBAC, approval, audit | security governance, data models, decision log, system architecture |
| Trace or dashboard | AgentOps observability, security governance, evaluation plan |
| Evaluation | evaluation plan, milestone acceptance, relevant domain design |
| Demo or interview narrative | interview master narrative and implemented behavior only |

The filenames for all authoritative documents are indexed in
`.agents/skills/current/SKILL.md` and the two planning README files.

## Impact Check Before Code Changes

Before editing, identify in working notes or the user update:

- active task ID and acceptance criteria;
- affected feature and owning module;
- architecture layer and trust boundary;
- reused kernel components;
- public schemas, persistence, or CLI contracts affected;
- positive, negative, and regression tests required;
- whether progress, architecture, feature scope, or decisions must change.

This impact check is transient. Do not create a report file for it.

## Broad Scan Triggers

Do not rescan the whole repository by default. A broad scan is justified when:

- architecture, dependency, release, or repository-wide cleanup is the task;
- the context map conflicts with code or tests;
- impact crosses several reusable-kernel boundaries;
- broad regression failures indicate an unknown dependency;
- a public contract, dependency, or trust boundary is being changed.

Otherwise inspect the routed plans, owning modules, callers, and tests only.

## Verification Commands

```bash
# Closest Enterprise tests
PYTHONPATH=src python3 -m pytest -q tests/enterprise

# Full regression
PYTHONPATH=src python3 -m pytest -q

# Working tree and whitespace audit
git status --short
git diff --check
```

Use narrower domain tests before the full suite. Do not use live providers or
network access in deterministic tests.

## Update Triggers

- Update `.agents/context/progress.json` for every progress-bearing task.
- Update this file only when architecture boundaries, feature ownership,
  context routing, stable risks, or common verification commands change.
- Update authoritative planning/design documents only when their contract or
  accepted status changes.
- Never paste task history, command logs, or per-run file lists into this file.
