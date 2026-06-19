# Post-GA Portfolio Roadmap

This document plans the work after the `v3.0` candidate. It does not add a new
enterprise product line. It turns the implemented platform into a credible,
runnable portfolio and interview project while keeping the enterprise GA gates
honest.

`v3.0` remains blocked on external GA evidence:

- independent security reviewer signature;
- operator-owned production-like deployment evidence;
- stable live-provider workflow evidence.

The portfolio track is separate. It can be completed by the repository owner
without claiming that those external gates were satisfied.

## Principles

1. Stop expanding product scope. Do not plan `v4.0` features.
2. Build one excellent offline demo before adding screenshots, GIFs, or live
   lanes.
3. Prefer reproducible text and JSON artifacts over hand-written evidence.
4. Keep `security-review-v3.0.md` and release notes honest: candidate means
   candidate.
5. Do not delete legacy or foundation docs unless references, ownership, and
   tests prove the removal is safe.

## Stage Overview

| Stage | Name | Goal | Status |
|---|---|---|---|
| v3.1 | Portfolio Release Framing | Separate portfolio readiness from enterprise GA approval | Planned |
| v3.2 | One-Command Demo | Ship one deterministic `pr-review` demo with transcript snapshots | Planned |
| v3.3 | Interview Case Study | Tie RAG, workflow, MCP, guardrails, HITL, observability, and eval to code | Planned |
| v3.4 | Recruiter README | Make the repo understandable in the first 90 seconds | Planned |
| v3.5 | Visual Assets and Live Lane | Optional screenshots/GIF/live-provider polish | Optional |

## v3.1 Portfolio Release Framing

**Goal:** make the release status legible without weakening the `v3.0` GA
blockers.

**Scope:**

- add this roadmap and backlog entries;
- add an external-gates document that explains what an agent cannot close;
- add a false-GA-claim hygiene test;
- add a separate `portfolio_track` in `progress.json`.

**Non-goals:**

- marking enterprise GA complete;
- fabricating reviewer signatures, production logs, or live-provider evidence;
- changing runtime behavior.

**Acceptance:**

- `current.stage` stays `v3.0` and `current.status` stays `blocked`;
- `portfolio_track.next_delivery_task` points at `v3.1.1-T1`;
- docs distinguish "portfolio release" from "enterprise GA";
- no checked-in document claims external GA gates are satisfied.

## v3.2 One-Command Demo

**Goal:** a reviewer can run one offline command and see a PR security review
with citations, approval gating, redacted trace, and audit evidence.

**Scope:**

- add a small `sac demo pr-review --offline` surface;
- reuse existing fixtures and governance behavior;
- produce deterministic transcript snapshots;
- redact timestamps, run IDs, hostnames, and other volatile fields.

**Non-goals:**

- live GitHub writes;
- live model providers;
- five demo flows in the first batch.

**Acceptance:**

- `uv run sac demo pr-review --offline` exits 0;
- transcript includes classification, retrieval citations, workflow nodes,
  approval-gated write refusal, and audit chain head;
- snapshot tests pass without network or provider credentials.

## v3.3 Interview Case Study

**Goal:** turn the implemented platform into a crisp 15-minute system-design
story that points to real code and tests.

**Scope:**

- add a secure-change platform case study;
- verify implementation claims against existing modules;
- add link/path integrity tests for narrative docs;
- add an architecture poster that reflects the current implementation.

**Non-goals:**

- inventing a new architecture;
- rewriting the decision log into marketing copy;
- adding new platform capabilities.

**Acceptance:**

- every major capability section cites at least one source file and one test;
- referenced paths resolve in CI;
- the architecture poster is small enough to keep in the repository and is
  referenced by README.

## v3.4 Recruiter README

**Goal:** make the first 90 seconds of the repository explain the project
accurately and confidently.

**Scope:**

- rewrite the root README around the implemented enterprise platform;
- include a 30-second quickstart;
- link to the demo, architecture poster, release status, security review, and
  interview materials;
- add README link integrity tests.

**Non-goals:**

- overpromising production GA;
- deleting historical docs as part of the README rewrite;
- adding a hosted demo.

**Acceptance:**

- README clearly says this is a `v3.0` candidate plus portfolio track;
- every internal README link resolves;
- the quickstart command is deterministic and uses offline fixtures.

## v3.5 Visual Assets and Live Lane (Optional)

This stage is optional and should not block portfolio final.

Possible work:

- console screenshots after the one-command demo is stable;
- a small GIF or linked video;
- a single opt-in live-provider eval lane that skips when secrets are absent.

Do not add this stage if it delays v3.4 or introduces brittle credentials,
network flakiness, or binary churn.

## Minimum Portfolio Final Cut

The minimum credible final cut is:

1. v3.1 complete;
2. one `pr-review` offline demo with transcript snapshot;
3. one case study that maps the platform to real code and tests;
4. root README rewritten with passing link checks;
5. full regression passing.

Recommended final label: `enterprise-v3.4.0-portfolio-final`.

