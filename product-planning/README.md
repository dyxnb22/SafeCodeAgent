# SafeCodeAgent Enterprise Planning

SafeCodeAgent Enterprise turns the finished SafeCodeAgent terminal coding agent
into an enterprise security engineering agent platform.

The old product proved the hard local invariants: policy-gated writes,
checkpoint and rollback, hash-chain audit logs, bounded context, multi-provider
LLM clients, MCP proposal gates, sandbox approval, project memory, and live
evaluation. This branch should reuse those assets while moving the product goal
from "safe local coding agent" to "auditable enterprise security workflow
agent".

## Product Thesis

Enterprises do not need another generic RAG chatbot. They need agents that can
take a security issue, PR, incident, or engineering request and drive it through
a governed workflow: gather context, retrieve policy, plan, call tools, propose
changes, verify, ask for approval at risk boundaries, and leave an audit trail.

## Primary Workstreams

1. RAG and knowledge grounding for security policies, code context, historical
   fixes, architecture docs, runbooks, and PR history.
2. LangGraph workflow orchestration for resumable, stateful, auditable agent
   runs with conditional routing and human interrupts.
3. Enterprise tool and MCP integration for GitHub, Jira, CI, document stores,
   scanners, and internal systems.
4. Security governance with policy gates, RBAC, approval tiers, secret
   redaction, prompt-injection resistance, sandboxing, and audit.
5. AgentOps observability and evaluation: traces, tool calls, retrieval
   evidence, cost, latency, failure taxonomy, and regression fixtures.

## Planning Files

Foundation (set the direction and shape):

- `product-vision.md` — target users, scenarios, and positioning.
- `roadmap.md` — MVP / Beta / Enterprise phase narrative.
- `implementation-backlog.md` — coarse-grained engineering themes.
- `interview-talking-points.md` — short technical narrative.

Executable planning (new, authoritative for delivery):

- `version-roadmap.md` — stage versions `v1.0`–`v2.0` with sub-plans
  (`v1.1.1`, `v1.1.2`, …). The single source of truth for the order
  of work.
- `milestone-acceptance.md` — engineering, product, security, eval,
  and demo gate criteria per stage.
- `execution-backlog.md` — PR-sized tasks with files, tests, and
  acceptance criteria, fully detailed for `v1.1`–`v1.4`.
- `interview-master-narrative.md` — structured interview material
  organized by talking points and demo flows.
- `decision-log.md` — durable record of architectural decisions
  with rationale, alternatives, and revisit triggers.
- `claude-code-execution-guide.md` — operating contract for any AI
  agent (Claude Code, Codex) executing tasks on this branch.

Technical design lives in `../enterprise-docs/`.
