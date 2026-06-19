# AgentOps and Observability Plan

**Implementation status (v1.9):** Executable contracts through v1.9 are implemented; see `.agents/context/progress.json` for live stage state.
This plan specifies what is recorded for every enterprise workflow
run, how it is structured, how it is rendered to humans, and how it
flows into the evaluation lane and the compliance evidence exporter.

The goal: anyone with the trace artifact can reconstruct *what
happened*, *why*, *who approved it*, and *what cost was incurred* —
without re-running the workflow.

Privacy and redaction are first-class. The default export profile
is strict; raw prompts and full file contents never appear unless
an explicit policy bit enables them.

---

## Capture Surfaces

Three layered surfaces. Each lower surface is derived from the one
above; nothing is reinvented.

1. **Trace events** — append-only `trace.jsonl` per run. Source of
   truth.
2. **Run timeline JSON** — assembled view per run; what the
   dashboard and evidence exporter consume.
3. **Markdown / static HTML dashboard** — human-readable
   presentation. Derived from the timeline.

The audit log (legacy hash chain) is a *parallel* sink for a subset
of trace events. The trace file and the audit log share event ids
for traceability; the audit log is the authoritative integrity
record.

---

## TraceEvent Schema

Implemented in `src/safecode/enterprise/trace/events.py` and
emitted by `src/safecode/enterprise/trace/emitter.py`.

```text
class TraceEvent(BaseModel):
    event_id: str            # deterministic: f"evt-{sha256(run_id, node, seq)[:24]}"
    run_id: str
    tenant_id: str
    node_id: str             # name of the emitting node, or 'orchestrator'
    seq: int                 # monotonic per run
    type: TraceEventType
    timestamp: str           # UTC ISO-8601
    actor_id: str | None
    policy_snapshot_id: str | None
    payload: dict[str, str | int | float | bool | list]
    redaction_applied: bool
    redaction_reason: str | None
    cost: NodeCost | None
    duration_ms: int | None
    schema_version: int      # starts at 1
```

`TraceEventType` enum:

```text
class TraceEventType(str, Enum):
    workflow_start = "workflow.start"
    workflow_end = "workflow.end"
    node_start = "node.start"
    node_end = "node.end"
    retrieval_query = "retrieval.query"
    retrieval_citation_used = "retrieval.citation_used"
    retrieval_permission_denied = "retrieval.permission_denied"
    model_call_start = "model.call_start"
    model_call_end = "model.call_end"
    model_validation_fail = "model.validation_fail"
    tool_proposed = "tool.proposed"
    tool_blocked = "tool.blocked"
    tool_executed = "tool.executed"
    sandbox_proposal = "sandbox.proposal"
    sandbox_executed = "sandbox.executed"
    approval_requested = "approval.requested"
    approval_decided = "approval.decided"
    approval_consumed = "approval.consumed"
    approval_rejected = "approval.rejected"
    policy_block = "policy.block"
    policy_project_override_blocked = "policy.project_override_blocked"
    patch_proposed = "patch.proposed"
    patch_applied = "patch.applied"
    rollback_executed = "rollback.executed"
    validation_run = "validation.run"
    validation_result = "validation.result"
    failure_recorded = "failure.recorded"
    memory_fact_used = "memory.fact_used"
    memory_injection_blocked = "memory.injection_blocked"
    redaction_hit = "redaction.hit"
    audit_anchor_written = "audit.anchor_written"
```

A subset of these mirror `AuditEventKind` in `data-models.md`.
That overlap is intentional: events that matter for integrity are
emitted to both the trace file and the audit chain. Other events
(e.g. `redaction.hit` count) stay in the trace only.

---

## Emitter Behavior

- Writes to `.sac/enterprise/runs/<run_id>/trace.jsonl` (append-only).
- Sequence number `seq` is monotonic within the run; the orchestrator
  owns the counter to avoid races (the workflow is single-threaded
  per run).
- Idempotent on `event_id`: re-emitting an event with the same id
  is a no-op (used during resume).
- Redaction applied before write: the redactor runs over each
  payload field of type `str`. Payload fields exceeding 2 KB are
  truncated with a marker and `redaction_applied=true` regardless
  of secret-pattern hits.
- Atomic file ops: write to a temp file and rename to guarantee
  no partial events on crash.

---

## Field-Level Redaction Policy

| Payload field | Strict profile | Standard profile | Debug profile (requires policy unlock) |
|---------------|---------------|------------------|----------------------------------------|
| Raw model prompt | Excluded | Hash + first 256 chars | Full text |
| Raw model output | Hash + first 256 chars | Full text up to 2 KB | Full text |
| File content | Excluded | Path + line range + hash | Full text up to 8 KB |
| Diff hunk | Path + range + hash | Path + range + first 64 lines | Full hunk |
| Tool inputs (args) | Redacted via redactor | Redacted via redactor | Redacted via redactor (always; secrets never echoed) |
| Tool outputs | First 256 chars + hash | First 2 KB + hash | First 8 KB + hash |
| Approval preview | First 1 KB | First 1 KB | First 4 KB |
| Citations text | First 256 chars | First 1 KB | First 4 KB |
| Cost/latency/duration | Always present | Always present | Always present |

Tests assert: in strict mode no field of length > 2 KB appears
verbatim in the trace file; the regex set for secret patterns
produces zero matches on a corpus of seeded secrets.

Profile is chosen by config key `trace.export_profile`. Debug
requires the policy unlock `allow_debug_traces=true` *and* a
`maintainer`-tier approval.

---

## Run Timeline JSON

Built by `src/safecode/enterprise/trace/timeline.py` from `trace.jsonl`,
state checkpoints, and approval records.

Shape (top level):

```json
{
  "timeline_schema_version": 1,
  "run_id": "run-...",
  "tenant_id": "local",
  "task_type": "pr_review",
  "status": "succeeded",
  "actor": { "actor_id": "user:diaoyuxuan", "roles": ["maintainer"] },
  "policy_snapshot_id": "pol-...",
  "summary": "PR security review of pr_sql_injection",
  "started_at": "...",
  "ended_at": "...",
  "duration_ms": 28341,
  "nodes": [
    {
      "name": "classify_request",
      "status": "ok",
      "started_at": "...",
      "ended_at": "...",
      "duration_ms": 12,
      "summary": "task_type=pr_review",
      "events": ["evt-..."],
      "artifacts": []
    },
    ...
  ],
  "citations": [
    {
      "citation_id": "cite-...",
      "source_id": "policy-secure-sql-001",
      "source_type": "security_policy",
      "path": "examples/enterprise/policies/secure-sql.md",
      "start_line": 12,
      "end_line": 44,
      "score": 0.81,
      "selection_reason": "lex=0.41,sem=0.62,cwe_match=CWE-89",
      "permission_verdict": "allowed",
      "freshness": "current",
      "hash": "sha256:...",
      "text_excerpt": "..."
    }
  ],
  "tool_calls": [
    {
      "call_id": "tool-...",
      "tool_name": "github_pr.fetch_pr",
      "tool_category": "read_network",
      "decision": "AUTO",
      "outcome": "ok",
      "duration_ms": 412,
      "cost": { "input_tokens": 0, "output_tokens": 0, "latency_ms": 412, "request_count": 1 },
      "events": ["evt-..."]
    }
  ],
  "approvals": [
    {
      "request_id": "approval-...",
      "action": "github_write_comment",
      "risk_tier": "high",
      "decision": { "decision": "GATE", "reason": "policy + tool spec", "policy_snapshot_id": "pol-..." },
      "status": "approved",
      "grant_id": "grant-...",
      "consumed_at": "...",
      "decision_actor": "user:maintainer"
    }
  ],
  "validation": {
    "ran": false,
    "summary": "no validation needed for report-only path"
  },
  "proposals": [
    { "kind": "pr_review_report", "ref": "report.md" },
    { "kind": "pr_comment_draft", "ref": "draft_comment.md" }
  ],
  "costs": { "by_node": { ... }, "total": { "input_tokens": 4321, "output_tokens": 980, "latency_ms": 28341, "request_count": 7 } },
  "safety_invariants": {
    "audit_chain_intact": true,
    "no_unauthorized_mutation": true,
    "no_policy_block_overridden": true,
    "no_grant_double_consume": true,
    "redaction_complete": true
  },
  "failures": []
}
```

Tests assert:

- `timeline_schema_version` is present and stable.
- Two consecutive serializations produce byte-identical JSON.
- Sensitive fields are absent or explicitly marked `"redacted": true`.

---

## Markdown Dashboard

Rendered by `src/safecode/enterprise/trace/render_markdown.py`.

Sections, in order:

1. **Summary**
   - Run id, tenant, task type, actor, policy snapshot, status,
     duration, total cost.
2. **Timeline**
   - Per-node table: name, status, duration, summary.
3. **Citations**
   - Grouped by source type. Each row: path:line-range, score,
     selection reason, permission verdict, freshness.
4. **Tool Calls**
   - Per call: tool, category, decision, outcome, duration, cost
     (no inputs/outputs except excerpt where allowed by profile).
5. **Approvals**
   - Per approval: action, risk tier, decision, status, actor,
     timestamps, decision note (truncated).
6. **Validation**
   - Test outcomes, scanner re-run diff (if remediation), per-step
     duration.
7. **Cost and Token Summary**
   - Per node and total.
8. **Safety Invariants**
   - Green/red list with reasons on failures.
9. **Failures**
   - Per failure: category, node, message, recoverable, retry
     count.

CLI:

```
sac enterprise trace show <run_id> [--profile strict|standard|debug]
                                   [--out path]
                                   [--format markdown|html|json]
```

`html` is a static page rendering the same content; `json` returns
the underlying timeline JSON.

Sample header section:

```markdown
# Enterprise Run Dashboard

- **Run ID**: run-01HX...
- **Task**: pr_review
- **Actor**: user:maintainer (roles: maintainer)
- **Policy snapshot**: pol-01HX...
- **Started**: 2026-06-18T18:32:11Z
- **Ended**: 2026-06-18T18:32:39Z
- **Duration**: 28.3 s
- **Total cost**: 4321 in / 980 out tokens, $0.012 estimated

## Safety Invariants

- ✓ Audit chain intact
- ✓ No unauthorized mutation
- ✓ No policy block overridden
- ✓ No grant double-consume
- ✓ Redaction complete
```

---

## Failure Taxonomy

Categories used in `FailureRecord` and `failure.recorded` events.

| Category | Meaning |
|----------|---------|
| `model_validation` | LLM output failed Pydantic schema; one repair attempt allowed. |
| `retrieval_empty` | No citations returned after the second query round. |
| `tool_blocked` | Approval engine returned BLOCK or GATE without grant. |
| `tool_error` | Tool raised an exception (e.g. scanner schema mismatch). |
| `validation_failed` | Tests or scanner re-run failed post-apply. |
| `approval_rejected` | Human rejected. |
| `policy_block` | Policy engine refused (separate from BLOCK from tool spec). |
| `sandbox_refused` | Sandbox preflight refused. |
| `timeout` | Step exceeded latency budget. |
| `unknown_run` | Resume target run id is unknown. |
| `chain_mismatch` | Audit chain mismatch detected on resume. |
| `unknown` | Catch-all; tests assert this is rare and always logged. |

Each failure record references one or more `event_id`s for trace
walk-back.

---

## Cost and Latency Tracking

- Per-node `NodeCost`: input tokens, output tokens, latency ms,
  provider, request count.
- Per-run `RunCosts`: aggregation; `dollars_estimate` is derived
  from a static price table per provider (mock = 0).
- Latency budget per workflow lives in the policy as
  `cost_budget.<workflow>.max_latency_ms`. Exceeding it emits a
  `failure.recorded` of category `timeout` and finalizes the run
  with status `failed`.

---

## Replay and Debug Bundle

- A *replay bundle* is the entire `.sac/enterprise/runs/<run_id>/`
  directory zipped, with optional sibling `.sac/enterprise/policy/`
  snapshot. Replay is "you can re-render the dashboard", not "you
  can replay LLM calls".
- A *debug bundle* (when allowed) additionally includes raw model
  prompts and full file contents.
- Both are produced by the Compliance Export workflow (workflow 4)
  with an `evidence_export.zip` artifact.

---

## What Persists By Default vs Opt-In

| Artifact | Default | Opt-in via |
|----------|---------|------------|
| `trace.jsonl` (strict redaction) | Yes | n/a |
| `state.json` and per-node checkpoints | Yes | n/a |
| `timeline.json` | Yes | n/a |
| `report.md` | Yes | n/a |
| `draft_*.md` (e.g. draft PR comment) | Yes | n/a |
| Raw prompts | No | `trace.export_profile=debug` + policy unlock |
| Full file contents | No | Same |
| External telemetry export (OTel) | No | `trace.otel_endpoint` setting (post-v2.0) |
| Markdown dashboard `report.md` | Yes (per run) | n/a |
| Eval dashboard at `.sac/enterprise/eval/latest.md` | Only after eval run | `sac enterprise eval dashboard` |

---

## Telemetry Boundary

- No telemetry leaves the machine by default.
- The CLI never sends usage data to Anthropic, OpenAI, or any
  external service unless the user explicitly configures a provider
  with network access.
- The trace exporter writes locally only. OpenTelemetry is reserved
  as a swap at the emitter interface; not implemented before v2.0.

---

## Dashboard Evolution Plan

1. **Markdown** (v1.5.3) — what runs ship with. Stable schema.
2. **Static HTML** (v1.7+ as a small renderer) — same data, nicer
   display. Generated at trace show time; not a server.
3. **Local web UI** (post-v2.0, planned but not promised) —
   reads timelines from the same JSON; no schema change required.

The schema is the artifact, not the rendering. Future UIs must
consume the same `timeline.json`.

---

## How Observability Powers Other Layers

| Consumer | Consumes |
|----------|----------|
| Eval runner | `timeline.json` + `state.json` to compute assertions. |
| Compliance evidence | `trace.jsonl` (strict-redacted), `timeline.json`, audit chain segment, validation outputs. |
| Performance budget tests (v1.9.3) | `cost` and `duration_ms` from timeline. |
| `decision-log.md` updates | Significant `policy.block` or `policy.project_override_blocked` events. |

---

## Tests

| File | Asserts |
|------|---------|
| `tests/enterprise/trace/test_event_schema.py` | Event shape, redaction flag default. |
| `tests/enterprise/trace/test_emitter_idempotency.py` | Re-emit no-op. |
| `tests/enterprise/trace/test_timeline_round_trip.py` | Two serializations equal. |
| `tests/enterprise/trace/test_timeline_redaction.py` | No sensitive field leak. |
| `tests/enterprise/trace/test_render_markdown_sections.py` | All required sections present. |
| `tests/enterprise/trace/test_redaction_strict_default.py` | Default profile is strict. |
| `tests/enterprise/trace/test_redaction_debug_requires_policy.py` | Debug needs unlock + approval. |
| `tests/enterprise/cli/test_cli_trace_show.py` | CLI happy path. |

---

## Backwards Compatibility

- `timeline_schema_version` allows schema growth without breaking
  consumers.
- Breaking changes require:
  - Bump `schema_version`.
  - A migration note in `decision-log.md`.
  - A `tests/enterprise/contracts/test_public_contract_v2_0.py` update with
    `tests/enterprise/contracts/snapshots/timeline.json`.

---

## What This Plan Deliberately Excludes

- OpenTelemetry exporter (reserved).
- Web dashboard (reserved).
- Cross-run analytics dashboards (reserved; eval dashboard is the
  closest substitute).
- Real-time streaming traces to external sinks (reserved).
- User-supplied redaction patterns (reserved for v1.9.x or later).
