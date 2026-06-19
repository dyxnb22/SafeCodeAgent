# Decision Log

**Implementation status (v2.0 RC):** Decisions D1–D18 are in effect through
v2.0 RC. Decisions D19–D31 are post-RC and govern v2.1+ planning. See
`.agents/context/progress.json` for live stage state.
This file is the durable record of architectural and product
decisions for SafeCodeAgent Enterprise. Every entry follows the
same shape and is written as if a future contributor will read it
six months from now without the context that produced it.

Format:

- **ID** — `D<index>`, immutable.
- **Date** — when the decision was committed.
- **Decision** — what we are doing.
- **Rationale** — why we are doing it.
- **Alternatives considered** — what we did *not* do, and why.
- **Consequences** — what changes because of the decision.
- **Revisit trigger** — the concrete signal that should reopen the
  decision.

Decisions are immutable once entered. If a decision is reversed,
add a new decision that explicitly supersedes it and update this
file to list the superseding entry. Do not edit history.

---

## D1 — Use a two-level version structure (`vX.Y` and `vX.Y.Z`)

- **Date:** 2026-06-18.
- **Decision:** Plan with stage versions `v1.0`, `v1.1`, …
  and sub-plans `v1.1.1`, `v1.1.2`, …. Every sub-plan is sized for
  a single PR.
- **Rationale:** Earlier roadmaps in this branch used only stage
  versions, which made it impossible to track concrete PR-level
  progress. Sub-plans give Claude Code, Codex, and human
  contributors a single, executable handle.
- **Alternatives considered:**
  - Stage-only versions. Rejected because tasks at stage level were
    too coarse and led to dropped scope and silent re-prioritization.
  - Plain task lists (no versions). Rejected because we lose the
    ability to gate features behind acceptance.
- **Consequences:** Every sub-plan in `version-roadmap.md` lists
  files, tests, and acceptance. Every `execution-backlog.md` task
  rolls up to a sub-plan.
- **Revisit trigger:** If the average sub-plan grows beyond 1.5
  PR-days for two stages in a row, the structure is failing and we
  need a finer granularity.

---

## D2 — Do not restore legacy SafeCodeAgent docs to this branch

- **Date:** 2026-06-18.
- **Decision:** This branch keeps `product-planning/` and
  `enterprise-docs/` only. Legacy docs under `docs/`, demo
  walk-throughs, version notes, and release ledgers from the old
  product are not restored.
- **Rationale:** Legacy docs were already extracted into
  `enterprise-docs/legacy-assets.md` for the parts worth carrying
  forward. Keeping the old material in tree confuses readers about
  what the current direction is. The `main` and
  `archive/safecodeagent-final` branches remain as historical
  references for anyone who needs them.
- **Alternatives considered:**
  - Keep both. Rejected: every reader had to ask "is this still
    real?".
  - Delete completely from git history. Rejected: history matters.
- **Consequences:** All planning lives under
  `product-planning/` and `enterprise-docs/`. Any legacy reference
  must be a deliberate link to the archive branch.
- **Revisit trigger:** If we decide to ship a "history" doc as part
  of Enterprise, we can introduce a single `enterprise-docs/
  legacy-trail.md` summary — not the original docs.

---

## D3 — Build RAG before LangGraph workflow

- **Date:** 2026-06-18.
- **Decision:** Stage v1.1 (RAG MVP) precedes stage v1.2
  (LangGraph workflow MVP).
- **Rationale:** Workflow nodes need grounded evidence to reason
  over. Building the workflow first would force retrieval shape
  decisions to be guessed and then redone. RAG carries the typed
  citation that workflow nodes consume; designing it second would
  let workflow contracts drift.
- **Alternatives considered:**
  - LangGraph first. Rejected because node contracts depend on
    citation shape.
  - Both in parallel. Rejected because they would interact in
    half-finished states and force coupling between unfinished
    code paths.
- **Consequences:** PR review and remediation workflows are blocked
  on retrieval. The schedule reflects that; v1.1 cannot be skipped.
- **Revisit trigger:** If retrieval recall is "good enough" earlier
  than expected and workflow design solidifies before v1.1.4 lands,
  reorder remaining v1.1.x tasks (T2-T3) in parallel with v1.2.1
  *only after the citation model is frozen*.

---

## D4 — CLI + Markdown dashboard first; web UI later

- **Date:** 2026-06-18.
- **Decision:** Until v2.0, the user surface is a Typer CLI plus
  Markdown and static-HTML reports. No web server, no UI
  framework, no client-side state.
- **Rationale:** The artifact is the JSON schema for the run
  timeline. Anything rendered from that schema is just
  presentation. Shipping a web UI early adds a dependency tree, a
  deployment story, and a maintenance load that does not improve
  the safety or correctness of the agent. Markdown dashboards are
  easy to diff in PRs and are demoable on any machine.
- **Alternatives considered:**
  - Build a small web UI in v1.5. Rejected: requires HTTP server,
    auth model, and a build step we do not need for any v1.x
    capability.
  - Use a hosted dashboard product. Rejected: introduces an
    external dependency before v2.0 and violates the local-first
    rule.
- **Consequences:** Trace renderer outputs Markdown by default and
  static HTML on request. The eval dashboard is also Markdown.
  Anything beyond that ships post-v2.0.
- **Revisit trigger:** When external reviewers consistently ask
  for a web UI after v2.0, and the trace schema has been stable
  for two stage releases, then promote the static HTML path to a
  small read-only web app.

---

## D5 — Multi-agent only when output schemas differ

- **Date:** 2026-06-18.
- **Decision:** Roles (`SecurityAnalyzer`, `PolicyReviewer`,
  `CodeFixer`, `Validator`, `Reporter`) live as typed prompts at
  workflow nodes, not as separate agent processes. New roles
  require a new typed output schema.
- **Rationale:** Multi-agent chat between language models
  consumes tokens, adds synchronization issues, and rarely yields
  better outputs than well-prompted single-call nodes against
  structured schemas. Multi-agent earns its place when outputs
  must differ in *shape*, when concurrency is real, or when
  specialization is justified — none of which apply broadly here.
- **Alternatives considered:**
  - Full multi-agent chat. Rejected: high cost, low determinism,
    weak safety story.
  - Single-agent for everything. Rejected: blurs node outputs
    (analysis vs fix vs validation) and complicates schema
    validation.
- **Consequences:** The workflow design lists role responsibilities
  as schema bundles, not actors. Adding a new role is a code
  change with explicit typed output.
- **Revisit trigger:** If a future task type (e.g. red-team
  simulation) requires genuinely concurrent role agents with
  different schemas, introduce a new sub-graph node that runs them
  as parallel branches; do not retrofit the existing nodes.

---

## D6 — Policy, audit, and approval are foundational, not features

- **Date:** 2026-06-18.
- **Decision:** Policy precedence, RBAC, approval engine, audit
  chain, and redaction are part of the core architecture, not
  bolt-ons. No feature ships if it bypasses them.
- **Rationale:** Retrofitting safety is hard and expensive.
  SafeCodeAgent's strongest invariants come from structural gates;
  removing them to "ship faster" loses the product's reason to
  exist. The action matrix in
  `enterprise-docs/security-governance-plan.md` codifies this.
- **Alternatives considered:**
  - Add approval gates only for "important" actions. Rejected: the
    set of important actions grows unpredictably and we end up
    re-implementing the gate in many places.
  - Trust the model with low-risk actions. Rejected: even low-risk
    actions are still side effects we must audit.
- **Consequences:** Every connector, scanner, and MCP tool routes
  through the approval engine. Every workflow run carries a policy
  snapshot. Every state mutation produces an audit event.
- **Revisit trigger:** If a measured performance or UX cost
  becomes unacceptable in a specific category (e.g. retrieval
  source access prompts), narrow the policy default rather than
  remove the gate.

---

## D7 — Planning lives only in `product-planning/` and `enterprise-docs/`

- **Date:** 2026-06-18.
- **Decision:** All Enterprise planning lives under these two
  directories. The `docs/` directory contains only a short
  pointer; legacy docs are not restored.
- **Rationale:** Two directories with one purpose each give
  reviewers a clear mental map: "where is the plan?" → product;
  "where is the design?" → enterprise. Anything else (`docs/`,
  `examples/`, etc.) is for runtime artifacts, fixtures, or user-
  facing material.
- **Alternatives considered:**
  - Consolidate into one directory. Rejected: product planning and
    technical design have different audiences and different
    cadences.
  - Spread across many directories. Rejected: harder to discover;
    encourages drift.
- **Consequences:** The `README.md` files in both directories list
  every planning file. The `tests/enterprise/test_planning_present.py`
  test asserts the set.
- **Revisit trigger:** If we add a third category of planning
  (e.g. customer playbooks) and it does not fit either bucket, add
  a third directory rather than overload an existing one.

---

## D8 — LangGraph is an optional dependency behind `enterprise` extras

- **Date:** 2026-06-18.
- **Decision:** LangGraph is installed only via the `enterprise`
  optional extras flag (`uv sync --extra enterprise`). The
  deterministic unit-test default is a local in-process
  orchestrator that runs the same node contracts.
- **Rationale:** Avoids pinning the project to a specific LangGraph
  version for every test run; keeps CI fast; lets the runtime swap
  be tested explicitly via `WORKFLOW_RUNTIME=langgraph`.
- **Alternatives considered:**
  - Make LangGraph a hard dependency. Rejected: ties CI to a
    moving target and risks unrelated test failures.
  - Reimplement LangGraph in-house. Rejected: needless
    maintenance burden.
- **Consequences:** Workflow tests run in two modes;
  pyproject extras section is non-empty; users without the extras
  get the local orchestrator only.
- **Revisit trigger:** If a future LangGraph feature becomes
  required for a workflow contract (not a runtime detail), promote
  it to a hard dependency.

---

## D9 — Approval grants are single-use and snapshot-bound

- **Date:** 2026-06-18.
- **Decision:** Every approval grant is consumed exactly once and
  references the `policy_snapshot_id` at grant time. Resuming a
  workflow with a different snapshot revokes the grant
  automatically.
- **Rationale:** Reusable grants are a footgun. A snapshot-bound
  grant means a human review is tied to a specific policy state;
  changing policy between approval and execution invalidates the
  approval rather than silently inheriting it.
- **Alternatives considered:**
  - Persistent grants by policy. Rejected: invites accidental
    re-use after policy edits.
  - Time-bounded grants. Deferred to v1.9; orthogonal to
    single-use.
- **Consequences:** Approvals must be explicit; resuming with a
  changed snapshot will fail with a typed error and require a new
  request.
- **Revisit trigger:** If a workflow pattern emerges that
  legitimately needs multi-step single-grant usage, introduce a
  "grant scope" concept rather than relaxing single-use.

---

## D10 — Server-claimed MCP tool metadata is ignored

- **Date:** 2026-06-18.
- **Decision:** The enterprise tool registry decides tool category
  and approval tier locally. MCP server `category` and similar
  fields are logged for debugging but not used for security
  decisions. Unknown tools default to `BLOCK`.
- **Rationale:** MCP servers are reachable across organizational
  boundaries and cannot be trusted to self-classify. A server
  flipping a write tool to `read` would otherwise bypass approval.
- **Alternatives considered:**
  - Trust server metadata. Rejected: violates the safety boundary.
  - Hybrid: trust some servers. Rejected: introduces a trust list
    that can grow; allowlist approach (explicit local entry)
    achieves the same goal more safely.
- **Consequences:** MCP onboarding requires an entry in the
  enterprise allowlist file. Adversarial eval cases verify the
  local classification holds under malicious server output.
- **Revisit trigger:** When a credible attestation mechanism for
  MCP servers exists (signed manifests, etc.), evaluate whether
  attested servers can short-circuit the manual allowlist.

---

## D11 — Strict trace redaction is the default; debug requires unlock and approval

- **Date:** 2026-06-18.
- **Decision:** The trace export profile is `strict` by default.
  Raw prompts and full file contents do not appear unless the org
  policy bit `allow_debug_traces=true` is set *and* a `maintainer`-
  tier approval grants the debug bundle.
- **Rationale:** Eval artifacts, evidence bundles, and replay
  bundles are intended to be shareable. The cost of accidental
  leakage is much higher than the cost of explicitly opting into
  debug mode when needed.
- **Alternatives considered:**
  - Standard profile by default. Rejected: too easy to leak by
    omission.
  - Debug profile by default for local users. Rejected:
    inconsistent with eval artifacts and compliance evidence.
- **Consequences:** Tests assert no field of length > 2 KB appears
  verbatim in default-profile artifacts. Debug bundles require two
  explicit consents.
- **Revisit trigger:** If repeated user friction emerges on
  debugging real workflow issues, evaluate adding a "diagnostic"
  profile that sits between standard and debug, with its own
  policy bit and approval tier.

---

## D12 — Live-provider eval is opt-in and non-blocking

- **Date:** 2026-06-18.
- **Decision:** The eval lane in CI runs against the mock provider.
  A separate `live_provider` pytest marker enables real-provider
  runs; these are opt-in and never block merges.
- **Rationale:** Live providers introduce rate limits, cost,
  non-determinism, and external availability concerns. None of
  these belong in a default CI path. Mock-provider eval covers the
  contract behavior (schemas, citations, approvals); live-provider
  eval is a separate, manual quality signal.
- **Alternatives considered:**
  - Run live in CI. Rejected: flaky, expensive, and security risk
    (token leakage).
  - Skip live entirely. Rejected: we still want the option to
    verify that real providers reproduce the deterministic results.
- **Consequences:** Two lanes; only one blocks merges; both
  document baselines.
- **Revisit trigger:** If a stable, deterministic real-provider
  setup becomes available (caching plus replay), evaluate making
  a curated live subset blocking.

---

## D13 — `tenant_id` is reserved on every model from the start

- **Date:** 2026-06-18.
- **Decision:** `tenant_id` (default `"local"`) appears on
  `EnterpriseRunState`, `RBACSubject`, `PolicySnapshot`,
  `KnowledgeSource`, and all retrieval indexes from v1.0 onward,
  even though multi-tenant enforcement does not arrive until v1.9.1.
- **Rationale:** Adding `tenant_id` later would require migrating
  every persisted artifact. Reserving the field is cheap; honoring
  it later is a matter of changing filters and enforcement, not
  schema.
- **Alternatives considered:**
  - Add only when multi-tenant arrives. Rejected: forces a
    migration of state, traces, audit log, and indexes.
- **Consequences:** Every model carries the field; tests assert it
  is present; v1.9.1 implementation flips it from cosmetic to
  enforced.
- **Revisit trigger:** If multi-tenant enforcement never lands,
  the field stays harmless. No downside.

---

## D14 — Yellow risks may carry forward at most three per stage

- **Date:** 2026-06-18.
- **Decision:** A stage gate may accept at most three documented
  yellow risks; everything else must close before the gate. The
  yellow risks must be listed in this file when accepted.
- **Rationale:** Without a hard cap, "yellow" becomes "yes, but
  later" by default, and the gate stops meaning anything.
- **Alternatives considered:**
  - No cap. Rejected.
  - Zero risks tolerated. Rejected: unrealistic, especially in MVP
    stages.
- **Consequences:** Stage gates explicitly enumerate yellow risks;
  carrying more than three forces re-prioritization.
- **Revisit trigger:** If post-v1.5 stages routinely accumulate
  three risks early, the underlying acceptance criteria are too
  ambitious and need a rewrite.

---

## D15 — The hand-rolled BM25-ish lexical scorer is good enough for v1.1

- **Date:** 2026-06-18.
- **Decision:** Implement lexical scoring in pure Python without
  adding a `rank_bm25` (or similar) dependency in v1.1.
- **Rationale:** Adding a dependency to ship a basic scorer is
  premature. The scorer is small; we can audit it directly and
  swap it later. Determinism in tests is preserved.
- **Alternatives considered:**
  - Add `rank_bm25` immediately. Rejected: no demonstrated need.
  - Skip lexical entirely. Rejected: pure semantic underperforms on
    rare terms and exact identifiers.
- **Consequences:** A small `lexical.py` module to maintain.
  Yellow risk recorded under v1.1.
- **Revisit trigger:** If retrieval recall regresses by more than
  2 percentage points on v1.6 baselines and we cannot attribute it
  to the corpus, swap to a library implementation.

---

## D16 — Pyproject dependencies stay tight in v1.0

- **Date:** 2026-06-18.
- **Decision:** v1.0 makes no changes to `pyproject.toml`. New
  optional dependencies (e.g. `langgraph`) land in v1.2.3 under
  the `enterprise` extras.
- **Rationale:** The planning stage should not move dependency
  versions. Doing so risks unrelated test churn before any
  Enterprise behavior exists.
- **Alternatives considered:**
  - Add `langgraph` early as a stub. Rejected: surprises
    contributors and CI for no benefit.
- **Consequences:** v1.0 PRs are doc-only or skeleton-only;
  dependency changes happen in clearly named tasks.
- **Revisit trigger:** None expected. If a new mandatory
  dependency emerges for a v1.x feature, document it as a separate
  decision.

---

## D17 — Reuse the legacy safety primitives without modification

- **Date:** 2026-06-18.
- **Decision:** Enterprise code under `src/safecode/enterprise/`
  imports and composes legacy primitives (`audit`, `sandbox`,
  `checkpoint`, `policy`, `context.redactor`, `mcp`, etc.) without
  modifying them.
- **Rationale:** The legacy modules carry the established safety
  invariants. Modifying them risks regressions in behaviors that
  are already tested. Composition keeps the primitives stable.
- **Alternatives considered:**
  - Refactor legacy into a shared base. Rejected: risk-reward
    poor; legacy is finished and the test surface is large.
  - Reimplement primitives in `enterprise`. Rejected: duplication
    and divergence risk.
- **Consequences:** Enterprise modules add adapters and registry
  surfaces; they never `Edit` legacy files. The full pytest suite
  remains green throughout.
- **Revisit trigger:** If a legacy primitive surfaces a real bug
  blocking enterprise use, file an issue and patch in a separate
  PR distinct from the enterprise work.

---

## D18 — The model never approves itself

- **Date:** 2026-06-18.
- **Decision:** No code path lets an LLM call decide an approval.
  Approvals are written by a human via the CLI inbox, never by
  any agent loop.
- **Rationale:** Self-approval is the trivially-broken case.
  Keeping the approval action human-only is the simplest possible
  guard.
- **Alternatives considered:**
  - "Auto-approve" with a trust score. Rejected.
  - Allow `AUTO`-tier actions to bypass approval altogether (already
    in design). Acceptable because `AUTO` is policy-decided, not
    model-decided.
- **Consequences:** CLI approval commands accept only human input;
  no programmatic path for the model to call them.
- **Revisit trigger:** None expected. Even with a trust framework
  later, the rule remains.

---

## D19 — PostgreSQL+pgvector is the persistent storage and vector store for v2.1+

- **Date:** 2026-06-19.
- **Decision:** Team Server and later deployment profiles use a single
  PostgreSQL instance for relational state and (from v2.4) a `pgvector`
  extension on the same instance for vector retrieval. No Qdrant,
  Milvus, Pinecone, or other vector store is introduced. No second
  relational store is introduced for OLTP traffic.
- **Rationale:** One database minimizes operational moving parts on
  on-prem deployments, lets approval consumption and audit append run
  in the same transactional boundary as the SQL state they reference,
  and keeps retrieval-row ACLs in the same enforcement layer as
  approvals and audit. `pgvector` is mature enough for the v2.4
  workload sizes and avoids a separate cluster, separate auth, separate
  backup story.
- **Alternatives considered:**
  - Qdrant or Milvus as a dedicated vector store. Rejected because they
    add a second cluster with its own identity, ACL, backup, and
    upgrade lifecycle for a feature that is not on the v2.1 critical
    path; v2.4 can revisit once the workload profile is known.
  - SQLite as the relational backend. Rejected because v2.1 needs
    `SERIALIZABLE` semantics for grant consumption under multiple
    workers, and SQLite's concurrency story does not support a real
    worker pool.
  - File-based persistent index. Rejected because tenant ACL is much
    weaker outside the database transaction.
- **Consequences:**
  - v2.1.3 lands the PostgreSQL backend; v2.4.1 adds `pgvector` on the
    same instance.
  - The legacy local file backend remains, but only for `local` mode
    (CLI) and tests.
  - Vector index size is bounded by what the operator allocates; the
    v2.4 plan documents the ratio of vector dimensions to row count to
    keep performance predictable.
- **Revisit trigger:** if v2.4 retrieval workloads exceed the
  documented pgvector envelope, or if a hosted profile demands a
  separately-managed vector store, file a new decision proposing a
  vector-store interface and migration plan rather than retrofitting a
  parallel store ad hoc.

---

## D20 — A single durable worker implementation backed by PostgreSQL queue tables

- **Date:** 2026-06-19.
- **Decision:** v2.1 introduces one worker implementation that pulls
  jobs from PostgreSQL queue tables using `SELECT ... FOR UPDATE SKIP
  LOCKED`. No Celery, Temporal, Dramatiq, or Redis is introduced.
- **Rationale:** The workload is per-run, low-frequency, and must share
  the transactional boundary with grant consumption and audit append.
  Introducing a separate broker adds an additional clock, identity,
  and failure surface without paying for itself at v2.1's scale. The
  in-database queue keeps worker recovery, lease, and idempotency in
  the same backup and migration story as the rest of the data.
- **Alternatives considered:**
  - Celery + Redis. Rejected because Redis becomes the durable state of
    record for in-flight runs and forces a second backup story; broker
    crashes do not currently appear in our threat model.
  - Temporal. Rejected because Temporal needs its own cluster and
    introduces a third identity boundary; benefits do not justify the
    cost at v2.1 scale.
  - Dramatiq. Rejected for the same reason as Celery + Redis with
    less ecosystem leverage.
- **Consequences:**
  - v2.1.5-T3 implements the lease and heartbeat in PostgreSQL with
    indexes on expiry.
  - v2.5.2 hardens the worker (DLQ, poison handling) inside the same
    in-database model.
  - We accept slightly higher write amplification on PostgreSQL in
    exchange for one operational surface.
- **Revisit trigger:** if the worker throughput requirement grows
  beyond what the in-database queue holds under load tests in v2.5.5,
  file a new decision proposing a broker, including a migration plan
  for the existing queue tables.

---

## D21 — FastAPI is the service boundary; CLI is a thin client in `server` mode

- **Date:** 2026-06-19.
- **Decision:** The v2.1+ service surface is FastAPI with Pydantic
  schemas and OpenAPI. The CLI keeps its existing local-mode behavior
  and gains a `server` mode that calls the same endpoints with the
  same JSON contracts. The API is the authoritative surface; the CLI
  never invents API behavior.
- **Rationale:** FastAPI maps cleanly to the typed contracts the
  enterprise code already uses; OpenAPI gives us a frozen surface for
  v2.3 and v3.0 consumers; sharing one schema between CLI and API
  avoids divergence. Choosing one framework here means we are not
  comparing FastAPI vs. Litestar vs. Flask later — that decision is
  taken now.
- **Alternatives considered:**
  - Litestar / Flask / Starlette. Rejected because FastAPI is the
    closest fit to our existing Pydantic-first model and is already a
    well-known operational target.
  - gRPC. Rejected because the consumer set is browser-based UI plus
    CLI and CI; HTTP/JSON is easier to debug and trace.
- **Consequences:**
  - v2.1.4 / v2.1.5 build under FastAPI; v2.1.7 freezes the API
    surface; v2.3 is built against the same endpoints.
  - CLI is a thin client in `server` mode; behavior parity is tested
    in v2.1.5-T4.
- **Revisit trigger:** if a real-time use case (e.g. streaming trace
  events to a UI without polling) cannot be served acceptably over
  HTTP/JSON, evaluate a parallel WebSocket or Server-Sent-Events
  endpoint behind the same auth boundary; do not abandon REST.

---

## D22 — `local` vs `server` runtime modes are an explicit setting, not auto-detected

- **Date:** 2026-06-19.
- **Decision:** A single `runtime_mode` setting (`local` or `server`)
  controls whether the CLI and the workflow use the file backend
  in-process or the v2.1 API + PostgreSQL backend. Auto-detection is
  not allowed. There is no third mode.
- **Rationale:** Auto-detection invites silent identity and policy
  switches. Explicit mode means a user knows which authentication is
  active, which storage is authoritative, and which audit chain
  records the run.
- **Alternatives considered:**
  - Auto-detect by environment. Rejected for the reason above.
  - Three modes (local / shared file / server). Rejected: shared file
    is not safe under multiple workers; we explicitly do not support
    it.
- **Consequences:**
  - The CLI prints the active mode in every run header.
  - Tests have a deterministic mode and never inherit the host's
    setting.
- **Revisit trigger:** none expected. If a customer profile genuinely
  requires a hybrid mode, the decision is reopened with a concrete
  threat model.

---

## D23 — Identity for v2.1+ is OIDC bearer tokens; server mode rejects `--actor`

- **Date:** 2026-06-19.
- **Decision:** Authenticated identity in `server` mode comes from an
  OIDC provider's bearer token. The CLI `--actor` flag is honored in local mode
  only and rejected in server mode so operators cannot mistake a display value
  for authenticated identity. The `RBACSubject` is built from validated claims.
- **Rationale:** v2.0 RC explicitly noted that trusting `--actor` is
  acceptable only for single-user local use. The team-server profile
  needs a verifiable identity; OIDC fits broadly without requiring a
  specific provider.
- **Alternatives considered:**
  - Static API keys. Rejected because keys are easy to leak and hard
    to rotate without a central revocation surface.
  - SAML. Rejected because the cost of supporting SAML for a CLI / UI
    workload is high and OIDC covers the common operator use cases.
- **Consequences:**
  - v2.1.6 implements OIDC validation and subject mapping.
  - The CLI reads tokens from the existing credential provider/keychain,
    `SAFECODE_ENTERPRISE_TOKEN` for bounded automation, or stdin. It does not
    accept a raw `--token` value that would leak through process listings or
    shell history; tokens never appear in logs or trace events.
  - SSO is layered on top of OIDC; the choice of provider is the
    operator's.
- **Revisit trigger:** if a regulated profile requires mTLS or SAML
  alongside OIDC, file a new decision and add the second boundary; do
  not weaken OIDC defaults.

---

## D24 — GitHub App credentials are loaded from environment / vault, never from the repo

- **Date:** 2026-06-19.
- **Decision:** The v2.2 GitHub App private key is loaded from a
  vault-backed secret (or, in local development, an environment
  variable). The key never appears in committed files, logs, traces,
  evidence bundles, or any persisted location. Rotation requires
  reloading the secret.
- **Rationale:** GitHub Apps are the right identity model for repo-
  scoped governed access; the private key is the high-value secret.
  Treating it as code-adjacent material is the trivially-broken case
  to avoid.
- **Alternatives considered:**
  - Per-user PATs. Rejected because PATs do not give us per-install
    permissions and rotation is harder to automate.
  - Repo-stored encrypted key. Rejected because it widens the blast
    radius if the repo is compromised.
- **Consequences:**
  - v2.2.1 enforces the credential boundary; a test asserts the secret
    never appears in any captured output.
  - Webhook signature secrets follow the same pattern.
- **Revisit trigger:** if GitHub introduces a workload-identity model
  (e.g. OIDC federation) that removes the need for a private key,
  file a decision migrating to it.

---

## D25 — LangGraph stays optional and behind the same runtime swap; v2.x does not depend on it for storage or persistence

- **Date:** 2026-06-19.
- **Decision:** v2.1 introduces durable storage but does *not* adopt
  LangGraph's hosted or persistent checkpointers as the workflow
  state-of-record. LangGraph remains an optional runtime, controlled
  by `WORKFLOW_RUNTIME`, that operates on top of the existing
  enterprise `EnterpriseRunState` and the persistence layer added in
  v2.1.2. Removing LangGraph still leaves a fully functional product.
- **Rationale:** Coupling state durability to a single library would
  make every later persistence decision LangGraph-shaped. Keeping the
  state in our own typed contract preserves the ability to swap the
  runtime if needed.
- **Alternatives considered:**
  - Adopt LangGraph's `Checkpointer` as the canonical backend.
    Rejected: ties our migration story to a moving target.
  - Drop LangGraph entirely now. Rejected: the abstraction still pays
    for itself on workflow visualization and conditional edges.
- **Consequences:**
  - v2.1.2 protocols define the state contract; LangGraph reads and
    writes through them.
  - The `local` runtime remains the deterministic default in CI.
- **Revisit trigger:** if LangGraph stabilizes a checkpointer API that
  encodes everything we already require *and* lowers our maintenance
  burden, file a decision to consume it.

---

## D26 — Web operator console is a separate React/Next.js application against the v2.1 API; no embedded UI

- **Date:** 2026-06-19.
- **Decision:** The v2.3 operator console is a separate React/Next.js
  application that consumes the v2.1 API. The FastAPI service does
  not serve a UI bundle directly. The UI repository / package is
  decoupled from the Python release lifecycle.
- **Rationale:** Mixing a Python release with a frontend build couples
  unrelated cadences. Separation also gives the UI its own type-safe
  schema generation from OpenAPI without pulling JavaScript tooling
  into the Python package.
- **Alternatives considered:**
  - Server-side rendered templates from FastAPI. Rejected: limited
    interactivity for a console with timelines and patch viewers.
  - Embed the UI assets in the Python package. Rejected: bloats the
    Python wheel and ties the UI release to the Python release.
- **Consequences:**
  - v2.3 ships in its own surface; the contract snapshot covers the
    UI/API boundary, not the UI internals.
  - CORS and CSRF defaults must be explicit in the API.
- **Revisit trigger:** if a hosted SaaS profile justifies bundling for
  operations, file a decision proposing a packaged distribution
  instead of changing the contract.

---

## D27 — Multi-agent expansion criteria (v2.x edition)

- **Date:** 2026-06-19.
- **Decision:** D5 stays in force: roles are typed prompt + schema
  bundles owned by nodes. v2.x may introduce additional roles only
  when (a) the output schema differs, (b) the data scope differs
  (different tenant or permission set), or (c) the specialization is
  justified by a concrete evaluation result. "We should add an agent"
  is not a justification.
- **Rationale:** Multi-agent chat between LLMs remains expensive,
  non-deterministic, and weakly justified for the workflows in scope.
  v2.4's `secure_planning` workflow may introduce a planning role
  with its own schema, but it must reuse the existing approval and
  retrieval gates.
- **Alternatives considered:**
  - Full multi-agent chat. Rejected, as in D5.
  - Specialist agents per workflow stage. Rejected because we already
    have typed nodes serving that purpose.
- **Consequences:**
  - v2.4.5 plans a `planning` role with its own typed output schema.
  - Any new role added later requires a matching eval case.
- **Revisit trigger:** a real workflow where concurrent agents with
  distinct schemas demonstrably outperform sequential nodes on an
  audit-friendly metric.

---

## D28 — Long-term memory admission, revocation, and expiry are first-class governance actions

- **Date:** 2026-06-19.
- **Decision:** Every fact admitted to v2.4's long-term memory
  requires an approval grant tied to the active policy snapshot, an
  explicit expiry, and an auditable revocation path. Untrusted text
  is never injected into the model without redaction and provenance.
- **Rationale:** Memory is a persistent attack surface. Without
  explicit admission and revocation, retrieved or learned content
  becomes implicit instructions over time. Tying admission to the
  approval engine reuses the v1.4 invariants we already trust.
- **Alternatives considered:**
  - Free-form memory writes by the agent. Rejected: violates the
    prompt-injection boundary by design.
  - Memory writes gated only by RBAC. Rejected: RBAC does not
    track per-fact provenance and expiry.
- **Consequences:**
  - v2.4.6 implements admission/revocation/expiry under the existing
    approval engine.
  - Each fact carries the policy snapshot at admission time and a
    revisit / expiry date.
- **Revisit trigger:** if memory is shown to be a frequent attack
  vector despite the gate, narrow the policy default rather than
  weaken the gate.

---

## D29 — API versioning is path-prefix `/v2`; v2.0 RC contracts remain valid through v2.x

- **Date:** 2026-06-19.
- **Decision:** All v2.1+ HTTP endpoints live under the `/v2` path
  prefix. CLI and trace / evidence / eval JSON schemas remain
  backwards compatible with v2.0 RC throughout the v2.x line; new
  fields are additive and snapshot-tested. Breaking schema changes
  are deferred to v3.0 GA with documented migration tests.
- **Rationale:** A stable contract is the only way the operator
  console and any third-party consumer can be developed without
  blocking on the agent service. Lifting the v2.0 RC freeze without
  notice would invalidate the security review we just filed.
- **Alternatives considered:**
  - No version prefix. Rejected: forces a v3 to require a full URL
    rewrite.
  - Per-endpoint versioning. Rejected: high maintenance, fragmented
    documentation.
- **Consequences:**
  - v2.1.7 snapshot tests cover the `/v2` surface.
  - v2.0 contract tests stay in place; any change requires a new
    decision plus a migration test before merging.
- **Revisit trigger:** if a security finding forces a breaking
  schema change, document the deviation in this log and update
  contract tests in the same PR.

---

## D30 — Team Server dependencies live in one lazy optional extra

- **Date:** 2026-06-19.
- **Status:** Accepted for v2.1.
- **Decision:** Add one `team-server` optional extra containing FastAPI,
  Uvicorn, pydantic-settings, psycopg 3 with pooling, HTTPX for bounded OIDC/JWKS
  retrieval, PyYAML for the OpenAPI contract loader, psycopg's binary runtime
  for slim containers, and PyJWT with cryptographic verification support. Base and
  `enterprise` extras remain unchanged. Team Server modules lazy-import these
  packages and perform no connection, discovery, or service startup at import
  time.
- **Rationale:** The Team Server requires a coherent tested dependency set, but
  forcing server, database, and identity packages onto local CLI users would
  enlarge the trusted and operational surface. Psycopg 3 provides sync/async
  PostgreSQL and pooling without adding an ORM; HTTPX and PyJWT keep OIDC
  discovery separate from token verification.
- **Alternatives considered:**
  - Put server dependencies in the base install. Rejected: breaks the local
    minimal-install contract and increases supply-chain exposure.
  - SQLAlchemy plus Alembic. Rejected for v2.1: repository protocols and
    explicit SQL own the schema; an ORM adds a second abstraction before it
    removes demonstrated complexity.
  - Authlib for the whole OIDC client. Rejected initially: the service only
    needs discovery/JWKS retrieval and JWT validation, not interactive OAuth
    flows. Revisit if v2.3 login requires a backend-for-frontend flow.
- **Consequences:**
  - `v2.1.1-T1` declares and locks the optional extra.
  - Production modules must remain importable in local mode when the extra is
    absent and raise a typed installation error only when server mode is used.
  - Supported ranges and lockfile changes are reviewed together.
- **Revisit trigger:** a required OIDC flow cannot be implemented safely with
  bounded HTTPX discovery plus PyJWT, or explicit SQL/pooling creates repeated
  transaction bugs that an ORM demonstrably prevents.

## D31 — Docker Compose is the v2.1 development and integration orchestrator

- **Date:** 2026-06-19.
- **Status:** Accepted for v2.1 development only.
- **Decision:** Use one checked-in Docker Compose profile for disposable
  PostgreSQL, API, and worker development/integration runs. Unit tests continue
  to use local backends and strict protocol fakes, but migrations, locking,
  `SKIP LOCKED`, and `SERIALIZABLE` acceptance require the real PostgreSQL
  integration lane. Compose is not the production deployment contract.
- **Rationale:** PostgreSQL transaction and concurrency behavior cannot be
  proven by an in-memory fake. Compose gives contributors and CI one repeatable
  database version without committing to Kubernetes or a hosted platform.
- **Alternatives considered:**
  - Fake-only database tests. Rejected: they cannot validate PostgreSQL DDL,
    isolation levels, row locks, or connection recovery.
  - Testcontainers as the sole orchestrator. Rejected initially: it adds a
    second Python dependency and hides the operator-visible stack; tests may
    wrap the same Compose profile later.
  - Kubernetes manifests in v2.1. Rejected: production orchestration is v2.5
    scope and would distract from service correctness.
- **Consequences:**
  - `v2.1.7-T2` lands the loopback-bound, secret-free development profile and
    upgrade/rollback rehearsal.
  - Real-PostgreSQL tests are marked and deterministic; they are required at
    milestone closeout even when the default unit lane skips Docker.
  - No Docker socket is mounted into the API or worker.
- **Revisit trigger:** CI cannot run Docker/Compose, or the on-prem v2.5 profile
  requires a production orchestrator. Any replacement must preserve the real
  PostgreSQL acceptance lane.

---

## D32 - GA security remediation may fail closed on unsafe legacy inputs

- **Date:** 2026-06-19.
- **Status:** Accepted for the v3.0 candidate remediation.
- **Decision:** Tenant identifiers use one path-safe ASCII contract across OIDC,
  API, persistence, worker, and memory. Live connector writes recognize only a
  target- and policy-bound single-use grant. Long-term memory admission requires
  the same grant plus explicit expiry; legacy database facts without those
  bindings migrate to `revoked`. Run command endpoints require at least the
  developer role. These security corrections may reject inputs that the
  pre-remediation candidate accepted.
- **Rationale:** Preserving acceptance of path traversal, caller-asserted
  approval, unauthorised run mutation, or unbound persistent memory would
  preserve vulnerabilities rather than compatibility. The v2.0 RC data
  contracts remain additive and snapshot-tested; only unsafe behavior changes.
- **Alternatives considered:**
  - Keep permissive inputs with warnings. Rejected because execution and
    persistence boundaries must fail closed.
  - Trust all legacy memory rows. Rejected because their approval provenance
    cannot be reconstructed.
  - Rewrite old migrations. Rejected because forward-only deployed databases
    require a new compensating migration.
- **Consequences:**
  - Migration `008_memory_governance_binding.sql` records legacy provenance as
    unverified and revokes facts that lacked expiry.
  - Development OIDC keys are generated locally and never committed.
  - The pre-remediation `enterprise-v3.0.0` tag remains historical candidate
    evidence and is not an approved GA tag.
- **Revisit trigger:** a customer migration identifies a valid tenant namespace
  that cannot be represented by the canonical identifier; add an explicit,
  tested mapping layer rather than relaxing path safety.

---

## D33 - Portfolio release track is separate from enterprise GA

- **Date:** 2026-06-19.
- **Status:** Accepted for post-v3.0 planning.
- **Decision:** Add a `v3.1`-`v3.4` portfolio track for honest release
  framing, one-command demo, interview case study, and recruiter-facing README
  polish. Keep `v3.0` enterprise GA blocked until the external reviewer,
  production-like deployment, and live-provider evidence gates have real
  artifacts. Portfolio completion must not mutate those GA gates to complete.
- **Rationale:** The implemented platform is already feature-complete enough
  for a resume and learning project, but its value is hidden behind deep
  planning docs and incomplete external GA evidence. A separate portfolio track
  lets the repo become runnable and explainable without fabricating enterprise
  production claims.
- **Alternatives considered:**
  - Continue adding enterprise product features. Rejected: more scope would
    dilute the interview story and increase maintenance cost.
  - Mark `v3.0` GA complete after local tests. Rejected: local tests cannot
    substitute for external review, production-like deployment evidence, or a
    live-provider run.
  - Put portfolio tasks directly into the main `current` progress state.
    Rejected: it would blur the blocked GA state and make future agents think
    the external gates were resolved.
- **Consequences:**
  - `post-ga-portfolio-roadmap.md` owns the portfolio narrative.
  - `execution-backlog.md` owns PR-sized portfolio tasks.
  - `progress.json` may add a separate `portfolio_track`, while `current`
    remains the enterprise GA state.
  - Root README and demo work may be treated as release-quality portfolio
    work, but not as enterprise GA evidence.
- **Revisit trigger:** real G1/G2/G3 artifacts are produced, or the project
  moves from portfolio use to an actual external customer rollout.

---

## How to add a new decision

1. Pick the next `D<n>` id.
2. Use the format above. Be specific. Avoid passive voice.
3. List at least two alternatives — the rejected branches matter.
4. Consequences must be concrete (what changes in code, in tests,
   or in workflow).
5. Revisit trigger must be measurable, not "if we feel like it".
6. Commit the decision with the PR that puts it into effect; never
   land a behavior change without the matching entry.
