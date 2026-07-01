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
- Last delivery stage completed: `v2.5 Production Hardening`.
- Current delivery stage: `v3.0` candidate blocked on external GA gates.
- Next delivery task: none; independent sign-off, deployment evidence, and a
  stable live-provider run are required before GA promotion.
- Portfolio track: **complete** (`v3.4` portfolio final). Delivered case study,
  architecture poster, recruiter README, and link hygiene. Enterprise GA
  blockers G1/G2/G3 remain pending; portfolio final does not close them.
- Post-RC platform architecture: `enterprise-docs/platform-architecture-v2.md`.
- Machine-readable live status: `.agents/context/progress.json`.

Do not infer current progress from prose in this file. Read `progress.json`.

## Source Precedence

Use sources in this order for Enterprise delivery work:

1. Security invariants and working rules in `AGENTS.md`.
2. Live task state in `.agents/context/progress.json`.
3. Accepted decisions in `product-planning/decision-log.md`.
4. Final architecture and domain contracts indexed by
   `enterprise-docs/README.md`.
5. Current code and durable tests for implemented behavior.

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

Concise architecture: `enterprise-docs/architecture.md`.
Detailed architecture: `enterprise-docs/platform-architecture-v2.md`.
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

## Implemented Capability Map

| Capability | Status | Primary reference |
|---|---|---|
| PR review, remediation, secure planning | Implemented | `enterprise-docs/workflow-design.md` |
| Permission-aware RAG and memory | Implemented | `enterprise-docs/rag-and-context.md` |
| Tools, MCP, GitHub, Jira, CI, scanners | Implemented | `enterprise-docs/mcp-and-tools.md` |
| Policy, RBAC, approval, audit, redaction | Implemented | `enterprise-docs/security-governance-plan.md` |
| Trace, evidence, evaluation | Implemented | `enterprise-docs/observability-and-evaluation.md` |
| Team Server and operator console | Implemented | `enterprise-docs/platform-architecture-v2.md` |
| Enterprise GA promotion | External gates pending | `enterprise-docs/security/external-gates.md` |

Version history belongs in Git and `progress.json`, not in this navigation map.

### Plane Map

| Plane | Owning module | Live source of truth |
|---|---|---|
| Service (FastAPI `/v2`) | `src/safecode/enterprise/api/` | `platform-architecture-v2.md` § Service plane |
| Workflow (durable worker) | `src/safecode/enterprise/worker/` | `platform-architecture-v2.md` § Workflow plane |
| Data (PostgreSQL + local file backend) | `src/safecode/enterprise/persistence/` | `platform-architecture-v2.md` § Data plane |
| Integration (live GitHub, Jira) | `src/safecode/enterprise/connectors/` | `platform-architecture-v2.md` § Integration plane |
| Identity (OIDC) | `src/safecode/enterprise/auth/` | `platform-architecture-v2.md` § Authenticated identity |

## Task-To-Context Routing

Read only the row needed for the active task, plus directly affected code and
tests.

| Task type | Required authoritative context |
|---|---|
| Prioritization or scope | decision log, final architecture, current code/tests |
| RAG, citations, or memory | RAG/context, data models, security governance |
| Workflow or state | workflow design, data models, platform architecture, security governance |
| Connectors, tools, scanners, MCP | MCP/tools, platform architecture, security governance |
| Policy, RBAC, approval, audit | security governance, data models, decision log |
| Trace, evidence, or evaluation | observability/evaluation, security governance |
| Demo or interview narrative | case study and implemented behavior only |
| Team Server API, persistence, worker, auth | platform architecture, decision log, security governance, data models |

The maintained document set is indexed in `enterprise-docs/README.md` and
`.agents/skills/current/SKILL.md`.

## Impact Check Before Code Changes

Before editing, identify in working notes or the user update:

- active task ID and requested outcome;
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

Otherwise inspect the routed context, owning modules, callers, and tests only.

## Verification Commands

```bash
# Closest Enterprise tests
uv run --extra enterprise python -m pytest -q tests/enterprise

# Full regression
uv run --extra enterprise python -m pytest -q

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
- Update maintained design documents only when their contract or accepted
  status changes.
- Never paste task history, command logs, or per-run file lists into this file.
