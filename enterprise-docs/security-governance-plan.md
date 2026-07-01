# Security Governance Contract

**Implementation status:** Implemented and maintained as the normative
governance contract for the v3.0 candidate.
This is the normative reference for policy, RBAC, approvals, audit,
secrets, and the action matrix used by the workflow's approval gate.
It anchors on the existing SafeCodeAgent safety kernel and adds only
what an enterprise workflow needs.

The single rule everything else derives from:

> The model can recommend. Policy decides. Approval executes.

---

## Policy Precedence

Layers, lowest to highest priority:

1. `workflow` — per-workflow overrides passed by the CLI
2. `env` — environment variables prefixed `SAC_ENTERPRISE_`
3. `project` — `<repo>/.sac/enterprise/project.yaml`
4. `user` — `~/.config/safecode/enterprise/user.yaml`
5. `org` — `~/.config/safecode/enterprise/org.yaml` (or
   operator-distributed Git-backed file when configured)

Higher-priority layers win. **A lower layer may not weaken a higher
layer**: if a higher layer sets a key to `BLOCK` or `GATE`, a lower
layer cannot upgrade it to `AUTO` or `CONFIRM`. The resolver rejects
weakening attempts and emits a `policy.project_override_blocked`
audit event with the offending key, the attempted value, and the
final value.

Each resolved key carries a structured rationale string referencing
the winning layer, so the audit trail explains why a decision held.

### Policy file shape

```yaml
# org.yaml example
version: 1
policies:
  file_write: GATE
  command_execute: GATE
  scanner_run: CONFIRM
  github_read: AUTO
  github_write_comment: GATE
  github_branch_push: BLOCK
  github_pr_create: GATE
  issue_comment: GATE
  mcp_read: CONFIRM
  mcp_write: BLOCK
  retrieval_source_access: AUTO
  memory_fact_inject: GATE
  policy_config_change: BLOCK
  production_access: BLOCK
  allow_as_role_flag: false
  allow_debug_traces: false
  protected_branches: ["main", "master", "trunk", "release/*"]
  network_allowlist:
    - "api.github.com"
    - "api.linear.app"
    - "jira.local"
  rag:
    max_citations_per_query: 8
    max_queries_per_node: 3
    max_citations_per_run: 24
  trace:
    export_profile: strict
```

---

## RBAC Model

| Role | Intent | Allowed approval surfaces |
|------|--------|---------------------------|
| `viewer` | Reads reports and allowed evidence | None; cannot approve. |
| `developer` | Runs local read tools and requests fixes | Can request approvals; can approve only `AUTO`-tier actions. |
| `security_reviewer` | Approves reports and low-risk patches | Approves `CONFIRM` and `GATE` actions that are `risk_tier ≤ medium`. |
| `maintainer` | Approves repo writes and PR creation | Approves all `GATE` actions including `high` risk. May approve `production_access`. |
| `platform_admin` | Configures connectors, policies, credentials | All approvals plus `policy_config_change`. |

### RBAC subject resolution

- The subject is built once at run start.
- Default source: `~/.config/safecode/enterprise/user.yaml` → `role:
  developer`.
- A CLI `--as-role <role>` is accepted only when org policy sets
  `allow_as_role_flag: true`.
- The subject is immutable for the run; a re-resolve requires a new
  `run_id`.

### Permission scopes vs roles

- **Role** decides what an actor can *approve* and what tools an
  actor can request.
- **Permission scope** decides what knowledge sources an actor can
  *retrieve* (see `permission_scope` on `KnowledgeSource`).
- Roles imply default scopes (e.g. `security_reviewer` ⊇
  `developer` scopes) but the org policy can list explicit scopes
  per role.

---

## Approval Tier Engine

The engine produces an `ApprovalDecision` for every tool call and
proposal action. Decision is the strictest of three inputs:

```
decision = max_strictness(
    policy_value(action),
    rbac_value(role, action),
    tool_spec_value(action),
)
```

Tier order (least strict → most strict): `AUTO < CONFIRM < GATE <
BLOCK`. The engine never relaxes; equal tiers tie at that level.

### Tiers in practice

| Tier | Behavior |
|------|----------|
| `AUTO` | Executes immediately, no prompt, no human required. Logged. |
| `CONFIRM` | Trust-mode aware. With trust enabled, executes; without, prints a one-line confirmation request. Logged. |
| `GATE` | Always pauses with `WorkflowInterrupted`. Requires a single-use grant. Logged. |
| `BLOCK` | Never executes. Workflow finalizes with `blocked`. Logged. |

Trust mode can lower interaction friction for `AUTO`/`CONFIRM` but
*cannot* bypass `GATE`/`BLOCK`. The legacy approval rules already
hold this; the engine reuses them.

### Grants

- A grant is a single-use token persisted at
  `.sac/enterprise/runs/<run_id>/grants/<grant_id>.json`.
- Consumption sets `consumed_at`; subsequent reads raise
  `GrantAlreadyConsumedError`.
- Grants reference the `policy_snapshot_id` at grant time. Resuming
  with a different snapshot revokes the grant automatically and
  forces a new request.

---

## Action Matrix

The matrix is normative. Tests assert this exact table. Changes to
the table require updating tests in `tests/enterprise/approvals/
test_decision_matrix.py` in the same PR.

Columns:

- **Action**: enum value from `Action`.
- **Default policy tier**: org-level default. Project policy may
  raise it (not lower).
- **Role permitted to approve**: minimum role.
- **Audit event**: kind emitted at decision and execution.
- **Side effects**: write/read/network/sandbox.

| Action | Default policy tier | Role permitted to approve | Audit event | Side effects |
|--------|---------------------|---------------------------|-------------|--------------|
| `file_write` | GATE | `maintainer` | `tool.proposed` → `approval.requested` → `approval.decided` → `tool.executed` / `tool.blocked` | local FS write; mandatory checkpoint and rollback. |
| `command_execute` (low risk) | CONFIRM | `developer` | same | local subprocess via sandbox proposal. |
| `command_execute` (high risk) | GATE | `maintainer` | same | local subprocess via sandbox; preflight check. |
| `scanner_run` (local) | CONFIRM | `developer` | same | local subprocess via sandbox. |
| `scanner_run` (networked) | GATE | `maintainer` | same | network call; allowlisted host. |
| `github_read` | AUTO | n/a | `tool.executed` | network read; redacted. |
| `github_write_comment` (fixture mode) | AUTO | n/a | same | local file write only. |
| `github_write_comment` (live) | GATE | `maintainer` | full chain | network write; allowlisted host. |
| `github_branch_push` (non-protected) | GATE | `maintainer` | full chain | network write. |
| `github_branch_push` (protected) | BLOCK | none | `tool.blocked`, `policy.block` | refused before network. |
| `github_pr_create` | GATE | `maintainer` | full chain | network write. |
| `issue_comment` (fixture) | AUTO | n/a | `tool.executed` | local write. |
| `issue_comment` (live) | GATE | `maintainer` | full chain | network write. |
| `mcp_read` (allowlisted server) | CONFIRM | `developer` | `tool.proposed` → `tool.executed` | local stdio or network; output redacted. |
| `mcp_read` (unknown server) | BLOCK | none | `tool.blocked` | refused. |
| `mcp_write` (allowlisted, low risk) | GATE | `maintainer` | full chain | server-defined effect. |
| `mcp_write` (unknown / high risk) | BLOCK | none | `tool.blocked`, `policy.block` | refused. |
| `retrieval_source_access` (in-scope source) | AUTO | n/a | `retrieval.query`, `retrieval.citation_used` | local read. |
| `retrieval_source_access` (out-of-scope) | BLOCK | none | `retrieval.permission_denied`, `policy.block` | refused before any return. |
| `memory_fact_inject` (admission) | GATE | security reviewer | `memory.fact_admitted` | persisted only after bound grant. |
| approved fact retrieval | AUTO | n/a | `memory.fact_used` | in-prompt with provenance and ACL. |
| `memory_fact_inject` (pending fact) | BLOCK | none | `memory.injection_blocked` | refused. |
| `policy_config_change` | BLOCK at org; GATE at `platform_admin` org only | `platform_admin` | full chain plus `policy.config_change` | local config write; never via model output. |
| `production_access` | BLOCK | `maintainer` after explicit `production_access_unlock` policy bit | full chain plus `policy.production_unlock` | network read/write to production hosts. |

### Rules baked into the matrix

- Reading is cheaper than writing; networking is more expensive than
  local.
- "Live mode" of any connector is always at least `GATE`; "fixture
  mode" never costs more than `AUTO`.
- Anything touching `protected_branches` is `BLOCK` regardless of
  role.
- Anything that would alter `policy` files is `BLOCK` for non-
  admins; admin path requires both an org policy unlock and an
  approval.
- Anything sending data outside the local repo (`production_access`,
  `mcp_write`, `github_branch_push`, `github_pr_create`) is at least
  `GATE`.
- Anything that *interprets data* from outside (read tools, MCP
  reads, retrieval) is `AUTO` or `CONFIRM` because the content is
  treated as data, not authority.

---

## Audit Requirements

The legacy audit logger and external anchor are reused unchanged.
The enterprise layer adds a typed taxonomy (see `data-models.md`,
`AuditEventKind`).

Mandatory events per workflow run:

- `workflow.start`, `workflow.end` (one each).
- `node.start`, `node.end` (one each per executed node).
- `retrieval.query` (per retriever call).
- `retrieval.citation_used` (per citation pulled into a prompt).
- `model.call_start`, `model.call_end` (per LLM call).
- `model.validation_fail` (when structured output fails; one repair
  attempt logs both).
- `tool.proposed`, `tool.executed` or `tool.blocked` (per tool
  call).
- `approval.requested`, `approval.decided`, `approval.consumed` /
  `approval.rejected` (per approval flow).
- `policy.block` (when an action is refused by policy or RBAC).
- `policy.project_override_blocked` (when project policy attempted
  weakening).
- `sandbox.proposal`, `sandbox.executed` (per sandbox lifecycle).
- `patch.proposed`, `patch.applied`, `rollback.executed` (per
  mutation).
- `audit.anchor_written` (at workflow finalize).

The hash chain is verified by `tests/enterprise/audit/
test_hash_chain_intact.py`. Any tampering invalidates the chain.

External anchoring uses the legacy `src/safecode/audit/anchor.py`
path under `~/.local/state/safecode/audit/anchors/`. Anchors are
*outside* the repo root.

---

## Secret Redaction

- Loaders, the redactor, and the trace emitter all use
  `src/safecode/context/redactor.py`.
- Patterns include API tokens, GitHub PAT, common cloud keys, JWTs,
  email/password pairs, and known secret-file paths.
- Redaction happens at three points:
  1. **Loader output** before chunk storage.
  2. **Prompt assembly** before sending text to LLM.
  3. **Trace and export** before persistence.
- The redactor never echoes the redacted value. Detected hits emit
  `redaction.hit` (count only; no content).

---

## Sandbox and Network Policy

- Network is disabled by default. Live connectors require both:
  - `network_allowlist` entries naming the host.
  - The legacy network policy gate.
- Sandbox execution preserves the legacy proposal/preflight/
  approval/claim/execute/record lifecycle. The enterprise layer does
  not introduce a new sandbox backend; it only adds richer trace
  events.
- Scanner invocations always run through a sandbox proposal; no
  workflow node shells out directly.

---

## Protected Branch Policy

- `protected_branches` in org policy lists patterns (glob).
- Any `github_branch_push` whose target matches a pattern is `BLOCK`,
  regardless of role.
- The PR creation action checks the target branch; protected target
  → `BLOCK`.

---

## Production-Like Action Policy

- `production_access` is `BLOCK` by default.
- Org policy can set `production_access_unlock: true` and list
  allowed hosts in `network_allowlist`.
- Even after unlock, the action is `GATE` and requires `maintainer`.

---

## Compliance Evidence

The Compliance Export workflow (workflow 4) produces a bundle whose
acceptance criteria are:

- Trace JSON for each run, redacted at `strict` profile by default.
- Citations list referencing source ids and hashes (no content
  bodies).
- Approvals list with timestamps, actors, decisions, and policy
  snapshot ids.
- Audit chain segments covering the runs, with hash links
  verifiable against the external anchor.
- Validation results (test outcomes, scanner re-run outcomes).
- A README explaining how to verify the bundle (hash check
  instructions).

A *debug bundle* additionally contains raw model prompts and full
file contents when allowed. It requires both:

- Org policy `allow_debug_traces: true`.
- A `production_access`-tier approval from `maintainer`.

Without both, the export rejects the debug flag.

---

## Prompt Injection Defense

Defense in depth, ordered from upstream to downstream:

1. **Loaders** never parse instructions from content; they only
   redact secrets.
2. **Retriever** returns content as data; permission verdict is
   computed and attached.
3. **Prompt assembly** wraps retrieved content with explicit
   delimiters and a content-not-instruction header.
4. **Structured output** parses the LLM response into Pydantic
   models; free-text instructions in retrieved content cannot move
   the response outside the schema without failing validation.
5. **Approval engine** is the only path to side effects; no LLM
   output is execution authority.
6. **Eval suite** measures resistance: ignore-policy,
   reveal-secret, run-command, push-branch, redact-evidence,
   change-approval, change-policy, masquerade-as-policy (v1.6.3).

---

## MCP / Tool Safety

- Tool category is local code, never server data.
- The MCP allowlist (`examples/enterprise/mcp_allowlist.yaml`) maps
  `<server_id>:<tool>` to enterprise category and approval tier.
- Unknown tools default to `BLOCK`.
- Server-claimed `category` and `dangerous` flags are logged but not
  used for decisions. Tests assert this.
- Output is capped (4 KB) and redacted before model context.
- A server that emits `category: read` while the local allowlist
  says `mcp_write` keeps the local classification.

---

## Memory Fact Injection

- Approved facts in `src/safecode/memory/facts.py` may be injected
  only after a `memory_fact_inject = GATE` admission is consumed; retrieval of
  the resulting approved fact is automatic within its ACL.
- Pending facts are never injected; injection attempt is `BLOCK` and
  audit-logged.
- The set of memory keys allowed for injection is configurable per
  workflow type.

---

## Policy Config Change

- Project policy files cannot weaken org/user.
- Editing the org or user policy via the CLI is `BLOCK` unless:
  - Org policy permits `policy_config_change: GATE` for
    `platform_admin`.
  - The action is approved with a `maintainer`-or-higher grant.
- No LLM-driven path may edit a policy file; the CLI command that
  edits policy refuses input that looks LLM-authored (heuristic
  presence of a session id and a non-`platform_admin` actor).

---

## Risk Classifier and Tier Mapping

The workflow assigns a `RiskTier` to each finding and each plan
action.

| Signal | Effect on tier |
|--------|----------------|
| Finding severity = critical (scanner) | `critical` |
| Finding severity = high or matched CVE/CWE in policy | `high` |
| File-write touching `protected_files` (e.g. auth modules listed in policy) | escalate by one |
| Network call to non-allowlisted host | escalate to `BLOCK` |
| Plan touches `policy_config_change` | escalate to `critical` and `BLOCK` |

`protected_files` is configurable in org/user policy.

---

## Failure Modes the Governance Layer Must Handle

- **Conflict between layers.** Resolver emits a structured rationale
  for each merged key; tests assert no silent winner.
- **Missing policy file.** Default org policy is built-in (the
  matrix above with sensible defaults). User and project files are
  optional. The CLI warns when org policy file is missing.
- **Stale grant.** Resuming a workflow whose `policy_snapshot_id`
  changed forces a new request; the stale grant is marked
  `revoked_due_to_snapshot_change`.
- **Wrong role attempting approval.** Approver lacks the role for
  the action; CLI returns a typed error and writes an
  `approval.role_mismatch` audit event.
- **Approval rejected.** Workflow finalizes with `rejected`; the
  proposal stays in the report for human follow-up.
- **Audit chain mismatch on resume.** Workflow refuses to continue
  and surfaces a `policy.audit_chain_mismatch` event.
- **Network policy denying a host post-approval.** Tool call is
  blocked with `tool.blocked` and `policy.block`; the consumed
  grant is *not* refunded (defense in depth).

---

## What This Layer Is Not

- Not a configuration-management UI.
- Not a centralized policy distribution service.
- Not an identity provider. Team Server validates configured OIDC identities;
  the organization still owns its IdP.
- Not an external policy decision point such as OPA.
