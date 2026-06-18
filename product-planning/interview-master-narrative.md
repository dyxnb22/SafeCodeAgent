# Interview Master Narrative

This is the structured material to draw from in interviews about
SafeCodeAgent Enterprise. It is not a script. Each section gives
the talking-point framing, the engineering detail to support it,
and the artifacts in the repo a reviewer can open.

The reference repo for everything below is the `dev/enterprise-
agent-platform` branch.

---

## One-Minute Pitch

> SafeCodeAgent Enterprise is a governed security engineering
> agent platform. It turns security findings, pull requests, and
> tickets into auditable workflows: retrieve grounded policy and
> code evidence, reason over the diff, propose a fix, run
> validation, pause for approval at risk boundaries, and leave an
> evidence trail.
>
> The product builds on the finished SafeCodeAgent safety kernel —
> policy-gated writes, checkpoint and rollback, hash-chain audit,
> proposal-style tool execution — and wraps it in a LangGraph-style
> workflow, RAG over security knowledge, RBAC and approval engine,
> typed MCP/connector layer, and trace + eval observability.
>
> It is not a security RAG chatbot. The model can recommend; the
> policy decides; the human approves; the audit records.

A reviewer should leave the minute knowing three things:
- Workflow, not chat.
- Safety is structural, not prompt-only.
- Everything is measurable.

---

## Architecture in Sixty Seconds

```
Interface (CLI) → Workflow (LangGraph) → Nodes (typed Pydantic)
                                ↘ RAG (permission-aware) ↗
                                ↘ Tools / MCP / Scanner Connectors ↗
                                ↘ Governance (Policy, RBAC, Approval) ↗
                                ↘ Audit + Trace (hash chain + JSON timeline)
                                ↘ Evaluation (deterministic + live smoke)
```

Talking points:

- The interface is intentionally CLI-first; the trace and dashboard
  are Markdown today and HTML/static next, and a web UI is *not* a
  prerequisite.
- The workflow is a state machine with checkpoints and resume, not
  a free-form agent loop.
- Tools are local *code* contracts; MCP server-claimed metadata is
  ignored for security decisions.
- The audit and approval primitives existed in the original
  SafeCodeAgent; the new layer is governance, RAG grounding, and
  workflow.

Reference: `enterprise-docs/system-architecture-v1.md`.

---

## Why This Is Not A Generic RAG Chatbot

Generic RAG chatbots:
- Retrieve and answer; one shot.
- No state, no resumability, no approvals.
- Tools, if any, are model-driven.
- Safety is prompt-only.

SafeCodeAgent Enterprise:
- Retrieves to *act inside a workflow*, not to chat.
- Carries typed state across nodes; resumes after interruptions.
- Tool authorization is decided by local policy, RBAC, and tool
  spec; the model is never authority.
- Approvals are single-use, audit-logged, snapshot-bound.
- Outputs are Markdown reports, JSON timelines, and approval
  artifacts, not chat turns.

If asked "what *is* a generic RAG chatbot good for", I answer:
answering a question. Our problem is doing the thing the question
implies. That gap is exactly what the workflow layer fills.

---

## Why LangGraph

I do not pull in a heavy framework casually. Three reasons it is
worth it here:

1. **Typed state machine.** Workflows need explicit state, not a
   blackboard. `EnterpriseRunState` is a Pydantic model the graph
   threads through nodes.
2. **Conditional edges + retries.** Security workflows branch:
   missing evidence → retrieve again; high risk → approval gate;
   validation fail → repair or block. LangGraph encodes these
   first-class.
3. **Checkpointing and resume.** Pausing for a human approval and
   resuming after a decision is a hard pattern to roll by hand
   safely.

I keep LangGraph behind an optional `enterprise` extras flag so the
deterministic unit tests run against a local orchestrator. The
LangGraph adapter consumes the same node contracts. This means I
can test the graph topology and the conditional edges separately
from the runtime choice.

Reference: `enterprise-docs/workflow-design.md`,
`enterprise-docs/system-architecture-v1.md`.

---

## How RAG Is Done

The retrieval layer is built to be useful for security, not
generic.

- **Source registry**: every knowledge source is registered with a
  type, owner, permission scope, refresh cadence, and parser. No
  drag-and-drop ingestion.
- **Loaders** are source-typed (markdown, code, SARIF, Semgrep,
  runbook). Each produces a `RawRecord`. No mixing.
- **Chunking** is heading-aware for docs and AST-aware for code.
  Chunk ids are deterministic, so re-indexing is idempotent.
- **Hybrid scoring** combines a small BM25-style lexical scorer
  with the existing embedding store. No third-party vector DB in
  MVP.
- **Permission-aware retrieval**: the `Citation` carries
  `permission_verdict`; restricted chunks never appear in results.
- **Citation packing**: every citation has source identity, line
  range, score, selection reason, permission verdict, freshness,
  and a hash. The dashboard renders them.
- **Prompt-injection defense**: retrieved content is wrapped as
  data, not instruction; the prompt-injection eval suite enforces
  this.
- **Cost discipline**: query count and citation count are capped
  per workflow; the context budget packer rejects overflow.

A reviewer can open
`enterprise-docs/rag-implementation-plan.md` and trace each step to
a sub-plan from v1.1.1 to v1.1.4.

---

## Multi-Agent Discipline

I avoid multi-agent unless roles own different output schemas.
Concretely, the workflow uses five role bundles, but they are not
separate processes — they are typed prompts at specific nodes:

| Role | Owner node | Output schema |
|------|------------|---------------|
| SecurityAnalyzer | `analyze_security_risk` | `RiskAssessment` |
| PolicyReviewer | nested in `analyze_security_risk` | structured policy citations |
| CodeFixer | `propose_report_or_patch` (remediation) | `Proposal.kind = patch_diff` |
| Validator | `validate` | `ValidationResult` |
| Reporter | `propose_report_or_patch` (review path) | `Proposal.kind = report` |

Why this discipline: chatty multi-agent setups burn tokens and
introduce a synchronization problem. I prefer typed handoffs and
schema validation over agent-to-agent banter.

I explain this with the phrase "role names alone do not justify a
multi-agent architecture". Multi-agent matters when the outputs
have to differ in schema and when concurrency or specialization is
real. In a security workflow, the gains are mostly on planning and
fix proposal, both already separated by node.

---

## How MCP Is Integrated

The legacy SafeCodeAgent already has MCP discovery, stdio
transport, output redaction, and write proposal flow. I keep those
primitives and add an enterprise layer on top:

- **ToolRegistry**: a single registry that knows native tools and
  MCP tools. Approval tier is local code, not server data.
- **Allowlist**: an operator-supplied YAML maps `<server>:<tool>`
  to enterprise category and approval tier. Unknown tools default
  to `BLOCK`.
- **Server-claimed metadata is ignored** for security decisions.
  We assert this with adversarial eval cases.
- **Output redaction** and the existing 4 KB size cap apply.
- **MCP read** is at most `CONFIRM`; **MCP write** is at most
  `GATE`; unknown servers `BLOCK`.

A reviewer can open `enterprise-docs/security-governance-plan.md`
and read the action matrix to see exactly when each MCP call type
is allowed.

---

## How Safety Is Guaranteed

Safety in this product is structural. The legacy invariants stay
in place:

- Model output is never execution authority.
- Writes are proposals; checkpoints are taken before apply;
  rollback remains available; audit events form a hash chain with
  external anchors.
- Sandbox lifecycle: propose → preflight → approve → claim →
  execute → record.
- Secret redaction at three points: loaders, prompt assembly,
  trace/export.

The enterprise additions are also structural:

- Policy precedence is enforced by the resolver; project config
  cannot weaken org/user.
- RBAC subject decides who can approve what.
- Approval engine is the only path from a workflow to a side
  effect; grants are single-use and snapshot-bound.
- Prompt injection: retrieved content is data; the workflow
  validates structured outputs; the approval engine remains the
  authority.
- Tenant isolation in retrieval and audit (v1.9.1).
- Strict redaction profile for trace and eval artifacts; debug
  requires explicit policy unlock and an approval.

The eval suite measures all of this, not just retrieval recall.

---

## How HITL Is Designed

Approvals are first-class objects, not modal dialogs.

- Every gated action emits an `ApprovalRequest` with `action`,
  `risk_tier`, `target`, `preview`, `policy_snapshot_id`.
- The workflow raises `WorkflowInterrupted`; the orchestrator
  writes state and exits.
- The CLI inbox: `sac enterprise approval
  list/show/approve/reject/request-evidence/revoke`.
- Approvals can be: approve, reject, request more evidence, edit
  plan constraints (via a follow-up workflow run), or partial
  approve (a subset of proposals).
- A grant is single-use; resuming with a changed policy snapshot
  revokes it automatically.

This design comes from a hard preference: I want the human to see
exactly *what* they are approving with a preview, *why* the
workflow paused with a risk tier and snapshot reference, and *what*
their decision means with explicit terminal states (approved,
rejected, blocked, revoked).

---

## How Evaluation Is Done

The eval lane is deterministic by default and structural in shape.

- **Cases** are YAML files with `expected_evidence`,
  `expected_behavior`, `forbidden_behavior`, `safety_assertions`,
  and `cost_budget`.
- **Six suites** cover retrieval, security workflow, prompt
  injection, MCP/tool classification, PR review, and remediation.
- **Safety assertions** are a small library: `audit_chain_intact`,
  `no_unauthorized_mutation`, `no_policy_block_overridden`,
  `no_grant_double_consume`, `redaction_complete`.
- **Baselines** ratchet: pass-rate may not drop for safety assertions;
  retrieval metrics may drop ≤ 2 percentage points without an
  explicit baseline update.
- **Live provider smoke** is opt-in and never blocks merges.

Talk-track: I treat "the eval lane is green" as the only honest
release signal. A demo can be cherry-picked; a baseline cannot.

Reference: `enterprise-docs/evaluation-plan.md`.

---

## How Observability Is Done

- Every run emits a `trace.jsonl`.
- The orchestrator builds a `timeline.json` from trace + state +
  approvals.
- The Markdown dashboard is the default presentation; static HTML
  comes later; a web UI is *not* a prerequisite.
- Strict redaction is the default for export. Raw prompts and
  full file contents never appear unless a policy unlock plus an
  approval grant it.
- The compliance evidence exporter zips a redacted bundle the
  hash chain can verify.

A reviewer can run `sac enterprise trace show <run_id>` after a
demo and see exactly what happened.

Reference: `enterprise-docs/agentops-observability-plan.md`.

---

## Tradeoffs I Made

| Decision | Trade-off |
|----------|-----------|
| Workflow first, autonomy second | Less flashy "watch the agent run" demos, but resumable and auditable. |
| LangGraph optional | A dependency to manage; offset by an in-process orchestrator for tests. |
| Local-first storage (file + SQLite) | No "wow" service architecture; offset by every MVP demo running on a laptop. |
| Approval engine in the critical path | More user friction; offset by zero unauthorized writes by construction. |
| Hand-rolled BM25-ish scorer | Lower retrieval ceiling early; offset by no extra dependency and a clear upgrade path. |
| MCP server metadata ignored | Slightly more configuration work; offset by adversarial-eval-proven safety. |
| Strict redaction default | More boilerplate to enable debug; offset by safe sharing of every artifact. |
| Multi-agent only when output schemas differ | Less "lots of agents" theater; offset by less wasted tokens and fewer race conditions. |
| Live provider not in CI | Manual smoke pass to confirm; offset by deterministic CI that does not flake on rate limits. |
| Markdown dashboard before web UI | UI does not look glossy; offset by the schema being the contract, not the rendering. |

---

## Demo Flow A — PR Security Review

Time: 4–5 minutes.

```text
$ sac enterprise workflow run \
    --task pr_review \
    --input examples/enterprise/fixtures/pr_sql_injection/

[trace] classify_request -> pr_review
[trace] collect_repo_context -> PR-001 (2 hunks)
[trace] retrieve_policy_and_code -> 3 citations
[trace] analyze_security_risk -> risk=high (sql_injection)
[trace] plan_actions -> draft_comment (AUTO), live_post (GATE)
[trace] propose_report_or_patch -> report.md, draft_comment.md
[trace] validate -> skipped (report-only)
[trace] approval_gate -> awaiting approval

$ sac enterprise approval show approval-...
$ sac enterprise approval approve approval-... --note "verified by AppSec"
$ sac enterprise workflow run --resume run-...
[trace] approval_gate -> grant consumed
[trace] propose: pr_comment_post executed (fixture mode = local file)
[trace] finalize -> report.md
$ sac enterprise trace show run-...
```

What the reviewer should notice:

- The workflow paused at approval; no write happened until approval.
- The report includes citations from the policy and the code.
- The trace dashboard records every node and every cost.

---

## Demo Flow B — Vulnerability Remediation

Time: 5 minutes.

```text
$ sac enterprise workflow run \
    --task remediation \
    --input examples/enterprise/fixtures/semgrep_sql_injection.json

[trace] collect_repo_context -> 1 finding
[trace] retrieve_policy_and_code -> 2 citations
[trace] analyze_security_risk -> risk=high
[trace] plan_actions -> 1 fix_patch
[trace] propose_report_or_patch -> diff
[trace] validate_pre_apply -> tests pass
[trace] approval_gate -> awaiting approval

$ sac enterprise approval approve approval-... --note "minimal fix"

$ sac enterprise workflow run --resume run-...
[trace] checkpoint
[trace] apply_patch -> 1 file
[trace] validate_post_apply -> tests pass; scanner re-run: finding cleared
[trace] finalize_success -> report.md
```

What the reviewer should notice:

- Checkpoint is created before the patch is applied.
- Validation runs *after* apply; if it fails, rollback happens
  automatically.
- The audit chain captures every step.

---

## Demo Flow C — Compliance Evidence Export

Time: 2 minutes.

```text
$ sac enterprise workflow run \
    --task compliance_export \
    --input "runs=run-01HX...,run-01HY..."

[trace] collect_repo_context -> 2 runs
[trace] retrieve_policy_and_code -> snapshots
[trace] analyze_security_risk -> safety invariants ok
[trace] plan_actions -> bundle manifest
[trace] propose_report_or_patch -> evidence.md
[trace] validate -> hash chain ok
[trace] finalize -> bundle .sac/enterprise/evidence/bundle-...zip
```

What the reviewer should notice:

- A single zip captures every audit-relevant artifact, redacted.
- The bundle is verifiable independently via hash.

---

## Inheritance From The Original SafeCodeAgent

Specifically reused from the finished SafeCodeAgent:

- `src/safecode/audit/` for the hash-chain logger and anchor.
- `src/safecode/sandbox/` for the proposal/preflight/approve/
  execute/record lifecycle.
- `src/safecode/checkpoint/` for pre-mutation snapshots.
- `src/safecode/policy/` as the basis of the policy resolver.
- `src/safecode/agent/native_tools.py` and the GitHub read/write
  tools (without modification).
- `src/safecode/mcp/` for discovery, stdio transport, redaction,
  output cap, and write proposal flow.
- `src/safecode/context/` for budget, redaction, and selection
  reasons.
- `src/safecode/index/` for chunking, embedding backend, and store.
- `src/safecode/memory/` for approved fact injection.
- `src/safecode/eval/` for the pytest-based deterministic +
  opt-in live lane pattern.

What is new for Enterprise:

- The `safecode.enterprise` namespace (workflow, RAG layer, tool
  registry, approvals engine, audit taxonomy, trace, eval, CLI
  surface).
- The action matrix.
- The compliance evidence exporter.
- The role-based approval inbox.
- The eval suites (retrieval, prompt injection, tool
  classification, PR review, remediation, compliance export).

---

## Why This Project Fits 2026 Enterprise Agent Direction

I look at where teams shipping agents in 2026 land, not at agent
trends from two years ago:

- **RAG is plumbing**, not product. We use it as evidence
  grounding, not as the value proposition.
- **LangGraph-style workflows** are how teams ship resumable
  agents. We use the typed state and conditional edges; we keep an
  in-process orchestrator so tests do not depend on a framework.
- **Multi-agent is rare and disciplined.** Roles only exist when
  their outputs differ. No agent-to-agent chatter.
- **MCP** is the universal connector contract. We integrate
  through the existing local kernel and treat server data as
  untrusted.
- **HITL** is first-class with explicit approval inboxes and
  grants.
- **Guardrails** are structural and measurable; eval suites
  enforce them.
- **RBAC + policy engine** is layered (org > user > project >
  env > workflow) with no-weakening.
- **Audit logs** are a hash chain with external anchors, not
  ad-hoc JSON.
- **AgentOps observability** ships locally first: trace JSON,
  Markdown dashboard, evidence exporter.
- **Evaluation** is part of release evidence, with safety-critical
  ratchets.
- **CI/CD** runs the deterministic lane on every PR.
- **Scanner integration** (Semgrep, pip-audit) is normalized into
  typed findings, not pasted as logs.
- **Connectors** (GitHub, Jira, Linear, MCP) live behind an
  enterprise tool registry with capability scoping.

That is the shape of enterprise agent work I expect to be doing in
2026, and that is the shape of this product.

---

## How To Walk A Reviewer Through The Repo

If a reviewer is sitting next to me, this is the path I take:

1. Open `product-planning/version-roadmap.md`. Show the stage
   list, then drill into `v1.1.x` to demonstrate the level of
   detail.
2. Open `enterprise-docs/system-architecture-v1.md`. Walk the
   mermaid diagram.
3. Open `enterprise-docs/security-governance-plan.md`. Read out
   the action matrix.
4. Open `enterprise-docs/workflow-design.md`. Walk the PR review
   sub-graph.
5. Run the PR review demo (Flow A above).
6. Run `sac enterprise trace show <run_id>` and walk the
   dashboard.
7. Run `pytest tests/enterprise/eval -q` to show the suite.
8. Open the eval baseline file and explain the ratchet.

If they ask "what's left", I open the backlog file and point at
the next stage. No mystery.

---

## Common Questions And Short Answers

**Q: Why not chat first?**
A: Chat is a feature; workflow is the product. Chat is a thin
client over the workflow at a later stage if we want.

**Q: Why not start with a web UI?**
A: The contract is the JSON schema. UI is rendering. Markdown
dashboard, static HTML, then web UI; same contract.

**Q: What stops the model from running a command?**
A: The tool registry, the approval engine, and the legacy sandbox
gate. Three structural barriers. Eval suite proves it.

**Q: What if a knowledge source contains malicious instructions?**
A: It is treated as data. Eval suite has eight prompt-injection
cases, and the approval engine remains the only path to side
effects.

**Q: Why local-first instead of a hosted service?**
A: Because the safety story is provable on a laptop today, and
deployment profiles (team server, on-prem hybrid) reuse the same
modules at different storage and identity bindings. The
architecture does not change with scale.

**Q: How do you ensure no regression?**
A: Baselines per suite with safety ratchets that allow zero
regression on safety-critical assertions and ≤ 2 percentage points
on retrieval. CI runs the deterministic lane on every PR.

**Q: How do you handle credentials?**
A: They never enter Pydantic models. Connectors reference credential
store entries; the values stay in the OS keychain or environment.
Tests assert tokens do not appear in traces.

**Q: How is this different from a SAST?**
A: A SAST finds; this remediates. The remediation workflow consumes
SAST output as evidence and proposes minimal fixes with proof of
validation.

**Q: How do you know your eval is good?**
A: It tests behaviors I can write down — recall, grounding, no
write without approval, no execution of embedded instructions. The
question is not "is the model good", it is "did the workflow keep
its contracts".
