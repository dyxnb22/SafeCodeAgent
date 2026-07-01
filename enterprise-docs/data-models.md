# Enterprise Data Models

**Implementation status:** Maintained contract reference for the implemented
v3.0 candidate models.
This document is the human-readable map of the durable Enterprise contracts.
The Pydantic models under `src/safecode/enterprise/` are authoritative; tests
guard their public field sets and serialized shapes.

Conventions:

- All models are Pydantic v2 (since `pydantic` is already a project
  dependency).
- Identifiers are `str` of stable format: `<kind>-<ulid>` or hash-
  derived for deterministic ids.
- Times are ISO-8601 strings in UTC.
- `enum` fields are Python `enum.Enum` subclasses with explicit
  string values.
- Empty defaults are explicit (`Field(default_factory=list)` for
  lists; never mutable class attributes).
- Models are immutable when consumed by nodes; orchestrator applies
  patches to construct new state.

The "Reuse" column points to the legacy module that supplies the
underlying primitive (logger, redactor, etc.) so this document
remains anchored in the existing codebase.

---

## EnterpriseRunState

The top-level state passed between workflow nodes. Persisted as
JSON after each node.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | `str` | yes | Exact supported state schema version. |
| `run_id` | `str` | yes | Globally unique. ULID prefixed with `run-`. |
| `tenant_id` | `str` | yes | Defaults to `local`; validated at service and persistence boundaries. |
| `task_type` | `TaskType` | yes | `pr_review` \| `remediation` \| `secure_planning` \| `compliance_export`. |
| `status` | `WorkflowStatus` | yes | See enum below. |
| `actor_id` | `str` | yes | Local user identifier; resolved via RBAC subject. |
| `subject` | `RBACSubject` | yes | Resolved at start; immutable through run. |
| `policy_snapshot_id` | `str` | yes | References the persisted `PolicySnapshot`. |
| `request` | `RunRequest` | yes | Original CLI request. |
| `repo` | `RepoContext` | yes | Repo metadata. |
| `pull_request_evidence` | `PullRequestEvidence \| None` | no | Normalized PR input. |
| `issue_evidence` | `IssueEvidence \| None` | no | Normalized ticket input. |
| `citations` | `list[Citation]` | yes (default empty) | Evidence used by analysis. |
| `findings` | `list[SecurityFinding]` | yes (default empty) | Issues identified or ingested. |
| `risk_tier` | `RiskTier \| None` | no | Set by `analyze_security_risk`. |
| `plan` | `Plan \| None` | no | Set by `plan_actions`. |
| `proposals` | `list[Proposal]` | yes (default empty) | Report / patch / comment proposals. |
| `tool_calls` | `list[ToolCallRecord]` | yes (default empty) | All tool invocations attempted. |
| `approvals` | `list[ApprovalRecord]` | yes (default empty) | Pending and decided approvals. |
| `validation` | `ValidationResult \| None` | no | Set by `validate`. |
| `report` | `Report \| None` | no | Set by `finalize`. |
| `costs` | `RunCosts` | yes | Aggregated token + latency + dollar estimates. |
| `failures` | `list[FailureRecord]` | yes (default empty) | Typed failure entries. |
| `node_outputs` | `dict[str, NodeOutput]` | yes | Per-node typed output. |
| `audit_anchor_id` | `str \| None` | no | Set when the final audit anchor is written. |
| `created_at` | `str` | yes | ISO time. |
| `updated_at` | `str` | yes | ISO time. |
| `missing_evidence` | `bool` | yes | Retrieval/collection routing signal. |
| `validation_failed` | `bool` | yes | Validation routing signal. |
| `awaiting_human_approval` | `bool` | yes | Resume gate signal. |

**Persistence:** `.sac/enterprise/runs/<run_id>/state.json`.
**Security note:** never contains raw model prompts or full file
contents. Citations carry pointers, not bodies.
**Relation to legacy:** the run id pattern mirrors the legacy
agent run id but lives under `.sac/enterprise/runs/` instead of
`.sac/runs/`.

### Auxiliary enums

```text
class TaskType(str, Enum):
    pr_review = "pr_review"
    remediation = "remediation"
    secure_planning = "secure_planning"
    compliance_export = "compliance_export"

class WorkflowStatus(str, Enum):
    pending = "pending"
    running = "running"
    awaiting_approval = "awaiting_approval"
    succeeded = "succeeded"
    failed = "failed"
    rejected = "rejected"
    blocked = "blocked"
    cancelled = "cancelled"

class RiskTier(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"
```

---

## RunRequest

The normalized CLI input.

| Field | Type | Description |
|-------|------|-------------|
| `task_type` | `TaskType` | Same as in state. |
| `input_kind` | `Literal['pr_fixture', 'pr_live', 'finding_fixture', 'finding_live', 'ticket', 'repo_query']` | What the task ingests. |
| `input_ref` | `str` | Path or URL. |
| `actor_id` | `str` | CLI user. |
| `extra` | `dict[str, str]` | Free-form normalized flags. |

**Security note:** `input_ref` is treated as untrusted; never used as
shell input.
**Persistence:** embedded inside `EnterpriseRunState`.

---

## RepoContext

| Field | Type | Description |
|-------|------|-------------|
| `repo_root` | `str` | Absolute path. |
| `branch` | `str` | Current branch. |
| `commit_sha` | `str` | Resolved at run start. |
| `git_remote` | `str \| None` | Optional remote URL (no credentials). |
| `protected_branches` | `list[str]` | Names like `main`, `master`. |

**Security note:** never stores tokens.
---

## SecurityFinding

Normalized vulnerability data, produced by scanners or PR analysis.

| Field | Type | Description |
|-------|------|-------------|
| `finding_id` | `str` | `finding-<hash(source,rule,path,line)>`. Stable. |
| `source` | `Literal['semgrep', 'pip_audit', 'sarif', 'agent_analysis', 'manual']` | Where it came from. |
| `rule_id` | `str` | E.g. `python.lang.security.sql-injection`. |
| `severity` | `RiskTier` | Normalized severity. |
| `title` | `str` | Short description. |
| `description` | `str` | Long description; treated as untrusted content. |
| `cwe` | `str \| None` | Optional CWE number. |
| `cve` | `str \| None` | Optional CVE id. |
| `location` | `Location` | File, line range, and snippet hash. |
| `confidence` | `Literal['low', 'medium', 'high']` | Detection confidence. |
| `evidence_refs` | `list[str]` | Pointers to citations or tool call records. |
| `remediation_hint` | `str \| None` | Vendor-supplied suggestion. |
| `created_at` | `str` | ISO time. |

`Location` shape: `{path: str, start_line: int, end_line: int, snippet_hash: str}`.

**Security note:** the `description` and `remediation_hint` fields
are untrusted content. Anywhere they are inserted into a prompt
must include a delimiter and explicit content-not-instruction tag.
**Relation to legacy:** there is no direct legacy equivalent;
SafeCodeAgent represented scanner output ad hoc.
**Persistence:** embedded in `EnterpriseRunState.findings`.

---

## Citation

| Field | Type | Description |
|-------|------|-------------|
| `citation_id` | `str` | `cite-<hash>`. Deterministic. |
| `source_id` | `str` | Foreign key to `KnowledgeSource.source_id`. |
| `source_type` | `SourceType` | See `KnowledgeSource`. |
| `tenant_id` | `str` | Tenant boundary for retrieval and export. |
| `path` | `str` | File or document path. |
| `start_line` | `int` | 1-indexed. |
| `end_line` | `int` | 1-indexed. |
| `score` | `float` | Combined lexical + semantic score. |
| `selection_reason` | `str` | Human-readable why-included. |
| `permission_verdict` | `Literal['allowed', 'restricted_to_subject', 'denied']` | Result of permission check. |
| `freshness` | `Literal['current', 'stale', 'superseded', 'unknown']` | Set by source registry metadata. |
| `hash` | `str` | `sha256:` of the chunk text. |
| `text_excerpt` | `str` | Bounded (≤ 1 KB); for the dashboard. |
| `markdown` | `str` | Rendered citation with source identity. |

**Security note:** `text_excerpt` is the only content field; the
full text lives in the chunk store. The excerpt is redacted before
storage.
**Relation to legacy:** mirrors patterns in
`src/safecode/context/selector.py` (selection reasons) but adds
permission + freshness.

---

## KnowledgeSource

Describes a single source of retrievable knowledge.

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | `str` | Stable. E.g. `policy-secure-sql-001`. |
| `source_type` | `SourceType` | Enum. |
| `name` | `str` | Human label. |
| `path_or_uri` | `str` | Local path or URI. |
| `owner` | `str` | Org-policy reference. |
| `permission_scope` | `list[str]` | Scope tags an actor must have to read. |
| `refresh_cadence` | `Literal['static', 'daily', 'on_demand']` | Determines `freshness` decay. |
| `parser` | `Literal['markdown', 'code', 'sarif', 'semgrep', 'runbook']` | Loader name. |
| `metadata` | `dict[str, str]` | Free-form tags (e.g. `cwe: 'CWE-89'`). |

```text
class SourceType(str, Enum):
    security_policy = "security_policy"
    secure_coding_standard = "secure_coding_standard"
    architecture_doc = "architecture_doc"
    project_doc = "project_doc"
    code = "code"
    historical_fix = "historical_fix"
    scanner_finding = "scanner_finding"
    runbook = "runbook"
```

**Security note:** `permission_scope` is the only field that affects
retrieval visibility; an empty list means *no actor can retrieve*.
**Persistence:** manifest file at
`examples/enterprise/knowledge_sources.yaml`; deserialized at
process start.

---

## WorkflowNodeResult / NodePatch / NodeOutput

`NodePatch` is what a node returns; `NodeOutput` is what is stored in
state after the patch is applied.

```text
class NodePatch(BaseModel):
    node_name: str
    status: Literal['ok', 'soft_failure', 'fatal']
    state_updates: dict[str, Any]
    events: list[TraceEventDraft]
    cost: NodeCost
    duration_ms: int

class NodeOutput(BaseModel):
    node_name: str
    status: Literal['ok', 'soft_failure', 'fatal', 'skipped']
    summary: str
    artifacts: list[NodeArtifact]
    started_at: str
    ended_at: str

class NodeArtifact(BaseModel):
    name: str
    kind: Literal['citation_set', 'plan', 'proposal', 'validation', 'report', 'evidence']
    ref: str  # path or in-state field name
```

**Security note:** `state_updates` is validated against the
`EnterpriseRunState` schema before application; unknown keys fail.
---

## ApprovalRequest

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | `str` | `approval-<ulid>`. |
| `run_id` | `str` | Foreign key. |
| `tenant_id` | `str` | Tenant binding. |
| `action` | `Action` | Enumerated below. |
| `risk_tier` | `RiskTier` | Workflow-supplied. |
| `requested_by_node` | `str` | E.g. `approval_gate`. |
| `requesting_actor` | `str` | Actor id. |
| `target` | `dict[str, str]` | E.g. `{repo: 'a/b', branch: 'feature/x'}`. |
| `preview` | `str` | Bounded preview (≤ 4 KB). |
| `policy_snapshot_id` | `str` | At time of request. |
| `status` | `Literal['pending', 'approved', 'rejected', 'evidence_requested', 'revoked']` | |
| `created_at` | `str` | Creation time. |
| `decision_at` | `str \| None` | Decision time. |
| `decision_actor` | `str \| None` | Human decision actor. |
| `decision_note` | `str \| None` | Redacted rationale. |
| `request_hash` | `str` | Tamper-evident request digest. |
| `created_at` | `str` | |
| `decision_at` | `str \| None` | |
| `decision_actor` | `str \| None` | |
| `decision_note` | `str \| None` | |

```text
class Action(str, Enum):
    file_write = "file_write"
    command_execute = "command_execute"
    scanner_run = "scanner_run"
    github_read = "github_read"
    github_write_comment = "github_write_comment"
    github_branch_push = "github_branch_push"
    github_pr_create = "github_pr_create"
    issue_comment = "issue_comment"
    mcp_read = "mcp_read"
    mcp_write = "mcp_write"
    retrieval_source_access = "retrieval_source_access"
    memory_fact_inject = "memory_fact_inject"
    policy_config_change = "policy_config_change"
    production_access = "production_access"
```

**Security note:** `target` and `preview` are validated by the
approval engine; never trusted to override the policy decision.
**Persistence:** `.sac/enterprise/runs/<run_id>/approvals/<id>.json`.
**Relation to legacy:** mirrors `src/safecode/agent/pending_action.py`
shape but adds enterprise fields (risk tier, snapshot reference).

---

## ApprovalDecision

| Field | Type | Description |
|-------|------|-------------|
| `decision` | `Literal['AUTO', 'CONFIRM', 'GATE', 'BLOCK']` | The strictest of policy/RBAC/tool spec. |
| `reason` | `str` | Human-readable rationale. |
| `policy_snapshot_id` | `str` | At decision time. |
| `inputs` | `ApprovalDecisionInputs` | The triple that drove the decision. |

```text
class ApprovalDecisionInputs(BaseModel):
    policy_value: Literal['AUTO', 'CONFIRM', 'GATE', 'BLOCK']
    rbac_value: Literal['AUTO', 'CONFIRM', 'GATE', 'BLOCK']
    tool_spec_value: Literal['AUTO', 'CONFIRM', 'GATE', 'BLOCK']
```

**Security note:** the engine never returns less strict than the
maximum across inputs. Tests assert this.

---

## ApprovalRecord (state-side view)

Inside `EnterpriseRunState.approvals` we store the merged view:

| Field | Type |
|-------|------|
| `request_id` | `str` |
| `decision` | `ApprovalDecision` |
| `request_status` | `Literal['pending', 'approved', 'rejected', 'evidence_requested', 'revoked']` |
| `grant_id` | `str \| None` |
| `grant_consumed_at` | `str \| None` |

**Relation to legacy:** legacy approvals were per-action; enterprise
approvals are workflow-aware (carry `run_id` and snapshot id).

---

## ToolCallRecord

Every tool invocation, whether successful or refused.

| Field | Type | Description |
|-------|------|-------------|
| `call_id` | `str` | `tool-<ulid>`. |
| `run_id` | `str` | |
| `node_name` | `str` | Originating node. |
| `tool_name` | `str` | Registry key (e.g. `github_read`, `mcp:internal-jira:get_issue`). |
| `tool_category` | `Literal['read_local', 'write_local', 'command', 'read_network', 'write_network', 'admin']` | From tool spec. |
| `inputs_redacted` | `dict[str, str]` | Redacted view of inputs. |
| `decision` | `ApprovalDecision` | Decision when called. |
| `grant_id` | `str \| None` | If `GATE` was satisfied. |
| `outcome` | `Literal['ok', 'blocked', 'error', 'redacted_oversize']` | |
| `output_excerpt` | `str` | ≤ 2 KB. |
| `cost` | `NodeCost` | Tokens / latency. |
| `started_at` | `str` | |
| `ended_at` | `str` | |

**Security note:** `inputs_redacted` and `output_excerpt` always
pass through the redactor before persistence.
---

## AuditTraceEvent

The on-chain event written via the legacy hash-chain logger.

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | `str` | Deterministic, derived from (run_id, node, sequence). |
| `kind` | `AuditEventKind` | Enum. |
| `run_id` | `str` | |
| `actor_id` | `str` | |
| `payload` | `dict[str, str]` | Bounded; redacted. |
| `prev_hash` | `str` | Chain link. |
| `hash` | `str` | This event's hash. |
| `created_at` | `str` | |

```text
class AuditEventKind(str, Enum):
    workflow_start = "workflow.start"
    workflow_end = "workflow.end"
    node_start = "node.start"
    node_end = "node.end"
    retrieval_query = "retrieval.query"
    retrieval_citation_used = "retrieval.citation_used"
    model_call_start = "model.call_start"
    model_call_end = "model.call_end"
    model_validation_fail = "model.validation_fail"
    tool_call_proposed = "tool.proposed"
    tool_call_blocked = "tool.blocked"
    tool_call_executed = "tool.executed"
    approval_requested = "approval.requested"
    approval_decided = "approval.decided"
    approval_consumed = "approval.consumed"
    policy_block = "policy.block"
    project_override_blocked = "policy.project_override_blocked"
    sandbox_proposal = "sandbox.proposal"
    sandbox_executed = "sandbox.executed"
    patch_proposed = "patch.proposed"
    patch_applied = "patch.applied"
    rollback_executed = "rollback.executed"
    audit_anchor_written = "audit.anchor_written"
```

**Persistence:** legacy hash-chain log under
`.sac/enterprise/audit/<chain_id>.log`.
**Relation to legacy:** taxonomy is new; storage is legacy.

---

## EvaluationCase / EvaluationResult

| EvaluationCase | Type | Description |
|---|---|---|
| `case_id` | `str` | E.g. `pr_review.sql_injection_basic`. |
| `suite` | `Literal['retrieval', 'prompt_injection', 'tool_classification', 'pr_review', 'remediation']` | |
| `goal` | `str` | One-line. |
| `input_fixture` | `str` | Path. |
| `expected_evidence` | `list[str]` | Source ids expected to be cited. |
| `expected_behavior` | `list[str]` | E.g. "report risk tier ≥ high", "propose minimal patch". |
| `forbidden_behavior` | `list[str]` | E.g. "no shell escape", "no PR push without approval". |
| `safety_assertions` | `list[str]` | Hash-chain intact, no unauthorized write, etc. |
| `cost_budget` | `CostBudget` | Tokens, latency, dollars. |

| EvaluationResult | Type | Description |
|---|---|---|
| `case_id` | `str` | |
| `passed` | `bool` | |
| `expected_evidence_recall` | `float` | |
| `forbidden_behavior_triggered` | `list[str]` | Empty in pass. |
| `safety_assertion_failures` | `list[str]` | Empty in pass. |
| `cost_used` | `RunCosts` | |
| `notes` | `str` | |

**Security note:** evaluation result artifacts use the strict
redaction profile by default.

---

## PolicySnapshot

| Field | Type | Description |
|-------|------|-------------|
| `snapshot_id` | `str` | Hash of merged layers + sources. |
| `layers` | `list[PolicyLayer]` | Ordered, lowest-priority first. |
| `merged` | `dict[str, PolicyValue]` | Final map. |
| `created_at` | `str` | |

```text
class PolicyLayer(BaseModel):
    name: Literal['org', 'user', 'project', 'env', 'workflow']
    source_ref: str  # path or env var prefix
    values: dict[str, PolicyValue]

class PolicyValue(BaseModel):
    key: str
    value: Literal['AUTO', 'CONFIRM', 'GATE', 'BLOCK'] | str
    rationale: str | None
```

**Security note:** snapshot persisted under
`.sac/enterprise/policy/snapshot_<id>.json`; never modified
in place.
**Relation to legacy:** legacy `src/safecode/policy/` is the basis;
enterprise adds layer ordering and snapshot ids.

---

## RBACSubject

| Field | Type | Description |
|-------|------|-------------|
| `actor_id` | `str` | E.g. `user:diaoyuxuan`. |
| `tenant_id` | `str` | Defaults to `local`. |
| `roles` | `list[Role]` | At least one. |
| `permission_scopes` | `list[str]` | Drives retrieval visibility. |
| `metadata` | `dict[str, str]` | E.g. team name. |

```text
class Role(str, Enum):
    viewer = "viewer"
    developer = "developer"
    security_reviewer = "security_reviewer"
    maintainer = "maintainer"
    platform_admin = "platform_admin"
```

**Security note:** the subject is constructed once at run start and
is immutable. `--as-role` is rejected unless org policy allows it.
---

## ConnectorConfig

A single connector's configuration.

| Field | Type | Description |
|-------|------|-------------|
| `connector_id` | `str` | E.g. `github`, `jira_local`, `mcp:internal-rag`. |
| `kind` | `Literal['github_pr', 'issue_markdown', 'issue_jira_json', 'semgrep', 'pip_audit', 'mcp']` | |
| `endpoint` | `str \| None` | URL or path. |
| `auth_ref` | `str \| None` | Reference to a credential store entry. Never the secret itself. |
| `defaults` | `dict[str, str]` | Default flags. |
| `permission_scopes` | `list[str]` | Required scopes for the actor. |
| `approval_tier_overrides` | `dict[str, Literal['AUTO', 'CONFIRM', 'GATE', 'BLOCK']]` | Per-action tier; never weakens base. |

**Security note:** auth secrets *never* appear in the model.
**Persistence:** YAML under `~/.config/safecode/enterprise/connectors.yaml`.

---

## CostBudget / RunCosts / NodeCost

```text
class NodeCost(BaseModel):
    input_tokens: int
    output_tokens: int
    latency_ms: int
    provider: str  # 'mock' in tests
    request_count: int

class RunCosts(BaseModel):
    by_node: dict[str, NodeCost]
    total: NodeCost
    dollars_estimate: float | None
    started_at: str
    ended_at: str | None

class CostBudget(BaseModel):
    max_input_tokens: int
    max_output_tokens: int
    max_latency_ms: int
    max_dollars: float
```

**Security note:** the mock provider returns deterministic costs;
unit tests assert budgets to keep CI cheap.

---

## FailureRecord

| Field | Type | Description |
|-------|------|-------------|
| `failure_id` | `str` | |
| `category` | `Literal['model_validation', 'retrieval_empty', 'tool_blocked', 'tool_error', 'validation_failed', 'approval_rejected', 'policy_block', 'sandbox_refused', 'timeout', 'unknown']` | |
| `node_name` | `str` | |
| `message` | `str` | Redacted. |
| `retry_count` | `int` | |
| `recoverable` | `bool` | |

**Security note:** `message` passes through the redactor.

---

## Persistence and Lifetimes

| Model | Where | Lifetime | Eviction |
|-------|-------|----------|----------|
| `EnterpriseRunState` | `.sac/enterprise/runs/<id>/state.json` | Per run | Manual `sac enterprise workflow gc --older-than` |
| Node checkpoints | `runs/<id>/node_<n>_<name>.json` | Per run | Same |
| `ApprovalRequest` | `runs/<id>/approvals/` | Per run | Same |
| `Grant` | `runs/<id>/grants/` | Per grant | Auto-removed on consume |
| `AuditTraceEvent` | `.sac/enterprise/audit/<chain>.log` | Forever | Manual rotation only with operator action |
| `PolicySnapshot` | `.sac/enterprise/policy/snapshot_<id>.json` | Forever | Same |
| `EvaluationCase` | `tests/enterprise/eval/cases/` | In repo | Versioned |
| `EvaluationResult` | `.sac/enterprise/eval/results/` | Until next baseline update | Auto-rotated |
| `KnowledgeSource` manifest | `examples/enterprise/knowledge_sources.yaml` | In repo | Versioned |
| `ConnectorConfig` | `~/.config/safecode/enterprise/connectors.yaml` | User config | User-managed |
| `Citation` | Embedded in run state and timeline | Per run | With run |
| `SecurityFinding` | Embedded in run state | Per run | With run |
| `ToolCallRecord` | Embedded in run state | Per run | With run |

---

## Model Coverage Matrix

| Model | Defined by version | Implemented by version | Used by stages |
|-------|-------------------|------------------------|----------------|
| `KnowledgeSource`, `SourceType` | v1.1.1 | v1.1.1-T1 | v1.1+ |
| `Chunk`, `Citation` | v1.1.2 | v1.1.2-T1 | v1.1+ |
| `EnterpriseRunState`, `RunRequest`, `RepoContext` | v1.2.1 | v1.2.1-T2 | v1.2+ |
| `NodePatch`, `NodeOutput`, `NodeArtifact` | v1.2.1 | v1.2.1-T3 | v1.2+ |
| `ToolSpec`, `ToolRegistry` | v1.3.1 | v1.3.1-T1 | v1.3+ |
| `PullRequestEvidence`, `IssueEvidence` | v1.3.2/3 | v1.3.2-T1, v1.3.3-T1 | v1.3+ |
| `SecurityFinding`, `Location` | v1.3.4 | v1.3.4-T1 | v1.3+ |
| `PolicySnapshot`, `PolicyLayer`, `PolicyValue` | v1.4.1 | v1.4.1-T1 | v1.4+ |
| `RBACSubject`, `Role` | v1.4.2 | v1.4.2-T1 | v1.4+ |
| `ApprovalRequest`, `ApprovalDecision`, `Action`, `ApprovalRecord` | v1.2.4 + v1.4.3 | v1.2.4-T1, v1.4.3-T1 | v1.2+ extended at v1.4 |
| `ToolCallRecord` | v1.5.1 | v1.5.1-T1 | v1.5+ |
| `AuditTraceEvent`, `AuditEventKind` | v1.4.5 | v1.4.5-T1 | v1.4+ |
| `EvaluationCase`, `EvaluationResult` | v1.6.1 | v1.6.1-T1 | v1.6+ |
| `ConnectorConfig` | v1.3.x | v1.3.2/3 | v1.3+ |
| `CostBudget`, `RunCosts`, `NodeCost`, `FailureRecord` | v1.2.1 / v1.6.1 | v1.2.1-T2, v1.6.1-T1 | v1.2+ |

---

## Validation Rules That Apply Across Models

These rules are enforced by Pydantic validators and unit tests.
They are normative; any contradiction in code is a bug.

1. No model may contain a raw model prompt, full file content, or
   secret-bearing field. Excerpts are bounded; full bodies are
   referenced by hash and path.
2. Every `*_id` field follows `<kind>-<token>` shape; tests assert
   prefix presence.
3. Enums are explicit; using free strings where an enum exists is
   a validation error.
4. Timestamps are UTC ISO-8601; parsing of other shapes fails.
5. `policy_snapshot_id` referenced anywhere must exist on disk; the
   orchestrator checks before persisting state.
6. `request_id` and `grant_id` are unique within a run; duplicate
   create fails.
7. Lists default to empty; `None` is never a list default.
8. Free-form `metadata` dicts only contain JSON-serializable values
   (str, int, float, bool, list of same).
