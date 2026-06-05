# Version Summary

This is the short map of SafeCode Agent version history. Use it before opening
the full [version implementation matrix](../version_implementation_matrix.md).

## Current Baseline

- Current documented baseline: `v4.12.4` tracked-profile hotfix.
- Package/runtime metadata remains `4.12.3` until the next release-tag decision.
- Current product truth: [../project-final-status-and-roadmap.md](../project-final-status-and-roadmap.md).
- Active forward cleanup: [../version-plans/post-v4.12-consolidation-roadmap.md](../version-plans/post-v4.12-consolidation-roadmap.md).

## Major Trains

| Train | Status | What It Established | Primary References |
| --- | --- | --- | --- |
| v4.12.x | complete | FastAPI todo demo, deterministic transcript, resume-MVP cut, tracked demo profile | [v4.12.4 note](../version-notes/v4.12.4-fastapi-todo-profile.md), [status](../project-final-status-and-roadmap.md) |
| v4.11.x | complete | agentic-lite loop, typed step projection, validation loop, agentic resume and smoke | [agent tutorial](../tutorials/agent-run-first-hour.md), [v4.11.5 note](../version-notes/v4.11.5-agentic-workflow-smoke.md) |
| v4.10.x | complete | DeepSeek preset, provider doctor diagnostics, retry reliability, opt-in live-provider smoke | [providers](../providers.md), [v4.10.4 note](../version-notes/v4.10.4-live-provider-smoke.md) |
| v4.9.x | complete | experimental local AI shell, natural-language router, project overview, AI shell smoke | [AI shell tutorial](../tutorials/ai-shell-first-hour.md), [v4.9.3 note](../version-notes/v4.9.3-ai-shell-docs-and-smoke.md) |
| v4.1-v4.8 | complete | task-first daily loop, profiles, fix-watch, resume/budgets, local git, memory, debug, tutorial guardrails | [shell-first roadmap](../version-plans/v4.1-to-v4.8-shell-first-roadmap.md), [command reference](commands.md) |
| v4.0 | complete | contract cut with zero breaking v3.0 public-contract changes | [public contracts](../public-contracts.md), [v4.0.0 note](../version-notes/v4.0.0-contract-cut.md) |
| v3.x | complete | public-contract stabilization, providers, MCP read contract, docs/productization readiness | [version notes index](../version-notes/README.md), [v4 readiness audit](../archive/audits/commercial-v1-readiness-audit-v3.11.x.md) |
| v2.x | complete | hardening, release tooling, diagnostics, policy presets, sandbox previews, eval fixtures | [version notes index](../version-notes/README.md), [product audit](../archive/audits/product-audit-v2.6.21.md) |
| v0.x-v1.x | historical | initial ask/edit/apply/rollback loop, local policy-gated execution, approvals, session state | [early roadmap](../archive/roadmaps/release_roadmap_v0_1_to_v1_0.md), [version notes index](../version-notes/README.md) |

## What To Read

- New user path: [../mvp-user-guide.md](../mvp-user-guide.md).
- Command details: [commands.md](commands.md).
- Stable contracts: [../public-contracts.md](../public-contracts.md).
- Full implementation ledger: [../version_implementation_matrix.md](../version_implementation_matrix.md).
- Release-by-release archaeology: [../version-notes/README.md](../version-notes/README.md).

## Maintenance Rule

Keep this page short. Add only milestone-level version changes here; put release
details in [../version-notes/](../version-notes/) and acceptance-command detail
in [../version_implementation_matrix.md](../version_implementation_matrix.md).
