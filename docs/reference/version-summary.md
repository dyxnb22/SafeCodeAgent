# Version Summary

This is the short map of SafeCode Agent version history. Use it before opening
the full [version implementation matrix](../version_implementation_matrix.md).

## Current Baseline

- Current documented baseline: `v7.1.5` — v7 contract cut, agent productization, and eval maturity train complete.
- Package/runtime metadata is `7.1.5`.
- Current product truth: [../current-status.md](../current-status.md).
- Compact release ledger: [../release-ledger.md](../release-ledger.md).
- Current forward state: v7.0.0 remains the stable-contract cut; v7.1.5 adds
  single-command agent polish, read-only subagent roles, session/shell polish,
  and eval reporting without adding new stable contracts.

## Major Trains

| Train | Status | What It Established | Primary References |
| --- | --- | --- | --- |
| v7.0.x-v7.1.x | complete | second stable-contract cut, 23 stable contracts, v7.0.x productization, v7.1 eval maturity | [public contracts](../public-contracts.md), [release ledger](../release-ledger.md) |
| v6.1.0 | complete | real DeepSeek live eval, realistic demo, hooks MVP, diagnostics-aware context | [status](../current-status.md), [live eval](../evaluation.md), [release ledger](../release-ledger.md) |
| v6.0.0 | complete | second major contract cut; trust mode schema and session rollback promoted; zero v5.0 breaking changes | [public contracts](../public-contracts.md), [release ledger](../release-ledger.md) |
| v5.6.x-v5.8.x | complete | prompt engineering, live eval harness, golden demo, threat model review, subagent activation, sandbox promotion, cost guardrails, v6 prep | [release ledger](../release-ledger.md), [version implementation matrix](../version_implementation_matrix.md) |
| v5.0.x-v5.5.x | complete | first stable native-tool contract cut, trust modes, context intelligence, MCP bridge, PyPI release path | [release ledger](../release-ledger.md), [status](../current-status.md) |
| v4.17.x-v4.18.x | complete | streaming output, shell polish (readline/Markdown/diff), live connectivity, fuzzy matching, per-patch undo, agent-loop transparency, safety regression fix | [release ledger](../release-ledger.md), [planning history](../planning-history.md) |
| v4.14.x-v4.16.x | complete | provider profiles, model aliases, sac init, session model switching, keychain credentials, bare sac enters shell, 7-command help, config migration, error rewrites | [release ledger](../release-ledger.md), [planning history](../planning-history.md) |
| v4.12.x | complete | FastAPI todo demo, deterministic transcript, resume workflow cut, tracked demo profile | [release ledger](../release-ledger.md), [status](../current-status.md) |
| v4.11.x | complete | agentic-lite loop, typed step projection, validation loop, agentic resume and smoke | [agent tutorial](../tutorials/agent-run-first-hour.md), [release ledger](../release-ledger.md) |
| v4.10.x | complete | DeepSeek preset, provider doctor diagnostics, retry reliability, opt-in live-provider smoke | [providers](../providers.md), [release ledger](../release-ledger.md) |
| v4.9.x | complete | experimental local AI shell, natural-language router, project overview, AI shell smoke | [AI shell tutorial](../tutorials/ai-shell-first-hour.md), [release ledger](../release-ledger.md) |
| v4.1-v4.8 | complete | task-first daily loop, profiles, fix-watch, resume/budgets, local git, memory, debug, tutorial guardrails | [command reference](commands.md), [version implementation matrix](../version_implementation_matrix.md) |
| v4.0 | complete | contract cut with zero breaking v3.0 public-contract changes | [public contracts](../public-contracts.md), [release ledger](../release-ledger.md) |
| v3.x | complete | public-contract stabilization, providers, MCP read contract, docs/productization readiness | [release ledger](../release-ledger.md), [version implementation matrix](../version_implementation_matrix.md) |
| v2.x | complete | hardening, release tooling, diagnostics, policy presets, sandbox previews, eval fixtures | [release ledger](../release-ledger.md), [version implementation matrix](../version_implementation_matrix.md) |
| v0.x-v1.x | historical | initial ask/edit/apply/rollback loop, local policy-gated execution, approvals, session state | [release ledger](../release-ledger.md), [version implementation matrix](../version_implementation_matrix.md) |

## What To Read

- New user path: [../user-guide.md](../user-guide.md).
- Command details: [commands.md](commands.md).
- Stable contracts: [../public-contracts.md](../public-contracts.md).
- Full implementation ledger: [../version_implementation_matrix.md](../version_implementation_matrix.md).
- Compact release history: [../release-ledger.md](../release-ledger.md).
- Release-by-release archaeology: [../version_implementation_matrix.md](../version_implementation_matrix.md).

## Maintenance Rule

Keep this page short. Add only milestone-level version changes here; put compact
release entries in [../release-ledger.md](../release-ledger.md) and acceptance
command detail in [../version_implementation_matrix.md](../version_implementation_matrix.md).
