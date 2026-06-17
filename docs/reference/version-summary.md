# Version Summary

This is the short map of SafeCode Agent version history. Use it before opening
the full [version implementation matrix](../version_implementation_matrix.md).

## Current Baseline

- Current documented baseline: `v7.1.5` — v7 contract cut, agent productization, and eval maturity train complete.
- Package/runtime metadata is `7.1.5`.
- Current product truth: [../project-final-status-and-roadmap.md](../project-final-status-and-roadmap.md).
- Current forward state: v7.0.0 remains the stable-contract cut; v7.1.5 adds
  single-command agent polish, read-only subagent roles, session/shell polish,
  and eval reporting without adding new stable contracts.

## Major Trains

| Train | Status | What It Established | Primary References |
| --- | --- | --- | --- |
| v7.0.x-v7.1.x | complete | second stable-contract cut, 23 stable contracts, v7.0.x productization, v7.1 eval maturity | [public contracts](../public-contracts.md), [v7.0.0 note](../version-notes/v7.0.0-second-stable-contract-cut.md), [v7 notes](../version-notes/README.md) |
| v6.1.0 | complete | real DeepSeek live eval, realistic demo, hooks MVP, diagnostics-aware context | [status](../project-final-status-and-roadmap.md), [live eval](../demo/live-eval-summary.md), [v6.1.0 note](../version-notes/v6.1.0-portfolio-maturity.md) |
| v6.0.0 | complete | second major contract cut; trust mode schema and session rollback promoted; zero v5.0 breaking changes | [public contracts](../public-contracts.md), [v6.0.0 note](../version-notes/v6.0.0-major-contract-cut.md) |
| v5.6.x-v5.8.x | complete | prompt engineering, live eval harness, golden demo, threat model review, subagent activation, sandbox promotion, cost guardrails, v6 prep | [v5.6-v5.8 roadmap](../version-plans/v5.6-to-v5.8-product-roadmap.md), [v5.8.2 note](../version-notes/v5.8.2-v6-prep-baseline.md) |
| v5.0.x-v5.5.x | complete | first stable native-tool contract cut, trust modes, context intelligence, MCP bridge, PyPI release path | [v5.0.0 note](../version-notes/v5.0.0-first-stable-contract.md), [status](../project-final-status-and-roadmap.md) |
| v4.17.x-v4.18.x | complete | streaming output, shell polish (readline/Markdown/diff), live connectivity, fuzzy matching, per-patch undo, agent-loop transparency, safety regression fix | [v4.18.0 note](../version-notes/v4.18.0-diff-rendering-per-patch-undo.md), [shell UX roadmap](../version-plans/post-v4.16-shell-ux-roadmap.md) |
| v4.14.x-v4.16.x | complete | provider profiles, model aliases, sac init, session model switching, keychain credentials, bare sac enters shell, 7-command help, config migration, error rewrites | [v4.14.0 note](../version-notes/v4.14.0-provider-profile-ux.md), [usability roadmap](../version-plans/post-v4.14-usability-roadmap.md) |
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
