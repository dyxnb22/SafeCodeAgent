# v6.0.0 Stable Contract Candidates

**Status:** Assessment document — not a commitment. Each candidate must meet
evidence criteria before promotion.

## Budget

v6.0.0 churn budget: **≤ 5 new stable contracts, zero v5.0 breaking changes**.

---

## Candidate Assessments

### 1. Trust mode schema (`auto_edit`, `full_auto`)

| Field | Detail |
|---|---|
| First appeared | v5.1.0 |
| Stage | **Promote** |
| Current state | `sac shell --auto-edit`, `sac shell --full-auto` CLI flags. Not persisted to config. All behavior is session-scoped. |
| Evidence needed | Snapshot of trust-mode schema with invariant list: 10-file guard, session rollback, command preview delay, high-risk block. |
| Blocker | None. One release cycle complete. |

**Decision:** Promote to stable contract at v6.0.0.

---

### 2. `sac rollback --session <id>`

| Field | Detail |
|---|---|
| First appeared | v5.1.0 |
| Stage | **Promote** |
| Current state | `sac rollback --session <id>` rolls back all checkpoints from a session. |
| Evidence needed | Snapshot of rollback result schema. Verify session-scoped rollback invariants (reverse order, atomic, audit events). |
| Blocker | None. One release cycle complete. |

**Decision:** Promote to stable contract at v6.0.0.

---

### 3. MCP native tool bridge schema

| Field | Detail |
|---|---|
| First appeared | v5.4.0 |
| Stage | **Defer** |
| Current state | `MCPNativeToolBridge` wraps MCP tools as `NativeToolSpec` instances. Registered with `NativeToolDispatcher`. |
| Rationale | MCP tool bridge depends on the MCP server ecosystem, which is still evolving. The `mcp_<server>_<tool>` naming convention is provisional. Promoting now would lock in a naming scheme that may not scale. |
| Blocker | Naming convention needs ecosystem validation. |

**Decision:** Defer to v6.1 or later.

---

### 4. Git context API (v5.3.0)

| Field | Detail |
|---|---|
| First appeared | v5.3.0 |
| Stage | **Defer** |
| Current state | `ContextSelector._recent_files()` runs `git log -n50 --name-only`. Output is redacted and bounded. |
| Rationale | The API is an internal implementation detail of context collection, not a user-facing contract. The behaviour (which files get recency bonus) is heuristic and may change as context selection improves. |
| Blocker | Schema not finalised; internal heuristic, not external API. |

**Decision:** Defer. Do not expose as a user-facing contract before v6.0.

---

### 5. Cost cap config key (`cost.max_tokens_per_session`)

| Field | Detail |
|---|---|
| First appeared | v5.8.0 |
| Stage | **Tentative promote** |
| Current state | Config key added in v5.8.0. `CostConfig` model with default `None` (unlimited). Project config can lower but not raise. |
| Rationale | The config key is simple, lowering-only, and has a clear safety role. However it has zero release-cycle evidence (same release as v5.8). |
| Blocker | Needs at least one release cycle of evidence. |

**Decision:** Conditonal promote — approve at v6.0.0 only if the key has been
stable through v5.9.x (or sufficient real-world use). If no evidence, defer.

---

### 6. Sandbox execution contract (promoted at v5.7.1)

| Field | Detail |
|---|---|
| First appeared | v5.4.x (real exec previews); promoted at v5.7.1 |
| Stage | **Already stable** |
| Current state | Section 17 of public-contracts.md. Preflight + env gate + claim-execute lifecycle. |
| Rationale | Already promoted. No additional v6.0 action needed. |

**Decision:** No action (already stable).

---

### 7. Live eval harness (v5.6.1)

| Field | Detail |
|---|---|
| First appeared | v5.6.1 |
| Stage | **Defer** |
| Current state | `src/safecode/eval/live.py`. 5 fixtures. `check_ratchet()` baseline enforcement. |
| Rationale | Live eval is a development tool, not a user-facing product surface. The fixture format (Python callables) is specific to the SafeCode repo and would need a documented JSON schema before promotion. |
| Blocker | Not a user-facing API; no external consumer identified. |

**Decision:** Defer. Re-evaluate if external contributors request it.

---

### 8. Golden demo project (v5.6.2)

| Field | Detail |
|---|---|
| First appeared | v5.6.2 |
| Stage | **Defer** |
| Current state | `examples/golden-demo/` with transcript, portfolio doc, and run-demo.sh. |
| Rationale | The golden demo is portfolio material and a CI signal, not a stable API surface. |
| Blocker | Not a public contract. |

**Decision:** Defer. Never promote — it is a demo, not a contract.

---

## Summary Table

| # | Surface | v5.x debut | v6.0 decision |
|---|---|---|---|
| 1 | Trust mode schema (`auto_edit`, `full_auto`) | v5.1.0 | **Promote** |
| 2 | `sac rollback --session <id>` | v5.1.0 | **Promote** |
| 3 | MCP native tool bridge schema | v5.4.0 | **Defer** |
| 4 | Git context API | v5.3.0 | **Defer** |
| 5 | Cost cap config key | v5.8.0 | **Conditional promote** |
| 6 | Sandbox execution | v5.7.1 | Already stable |
| 7 | Live eval harness | v5.6.1 | **Defer** |
| 8 | Golden demo project | v5.6.2 | **Defer** (not a contract) |

**Approved for v6.0 promote:** #1, #2, #5 (conditional), plus #6 already stable.
**Total new stable contracts at v6.0:** 2–3 (within the ≤5 budget).
**Zero v5.0 breaking changes:** confirmed — all candidates are additive.
