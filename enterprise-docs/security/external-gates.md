# External GA Gates

This document records the `v3.0` enterprise GA gates that cannot be satisfied
by repository-local code generation or agent-written documentation.

The portfolio track may make the project easier to run, review, and present.
It does not close these gates.

## G1 Independent Security Reviewer Signature

- **Status:** pending.
- **Owner:** independent reviewer or formally assigned security reviewer.
- **Required evidence:** signed review artifact with reviewer identity, review
  scope, date, finding summary, and disposition.
- **Agent boundary:** an agent may prepare checklists and summarize findings,
  but must not claim reviewer approval or create a substitute signature.

## G2 Production-Like Deployment Evidence

- **Status:** pending.
- **Owner:** operator running the production-like environment.
- **Required evidence:** deployment command log or CI artifact, service health
  checks, migration result, rollback result, redaction confirmation, and
  retained evidence location.
- **Agent boundary:** an agent may write runbooks and validation scripts, but
  must not mark deployment evidence complete without operator-owned artifacts.

## G3 Stable Live-Provider Workflow Evidence

- **Status:** pending.
- **Owner:** operator with approved provider credentials and network policy.
- **Required evidence:** one stable live-provider run with provider name,
  redacted request/response metadata, workflow result, cost/latency summary,
  and failure-handling notes.
- **Agent boundary:** an agent may maintain deterministic offline tests and
  optional live lanes, but must not convert offline fixtures into live evidence.

## Portfolio Track Relationship

The portfolio track may complete with all three gates still pending. Its
acceptance criteria are reproducibility, clear documentation, deterministic
offline demos, and interview readiness.

Do not use "GA approved" without real evidence for G1, G2, and G3.
Do not use "production deployed" without that same evidence.
Do not use "externally signed" without that same evidence. Until then, the
correct status is `candidate` or `portfolio final`.
