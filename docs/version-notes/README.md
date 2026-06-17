# Version Notes

This directory is the release-completion ledger for SafeCode Agent.

Each file records what changed, what was tested, and which acceptance criteria
were satisfied for one release or patch train. These notes are historical
records; they are not the recommended first-read path for users.

## Start Elsewhere First

- Current product behavior: [../project-final-status-and-roadmap.md](../project-final-status-and-roadmap.md)
- Major train summary: [../reference/version-summary.md](../reference/version-summary.md)
- Stable public surfaces: [../public-contracts.md](../public-contracts.md)
- Implementation ledger: [../version_implementation_matrix.md](../version_implementation_matrix.md)
- Release workflow rules: [../version_skill_workflow.md](../version_skill_workflow.md)

## By Major Version

| Major | Count | Theme | Good Entry Points |
| --- | ---: | --- | --- |
| v7 | 6 | second stable contract cut, v7.0.x productization, and v7.1 eval maturity | [v7.1.0](v7.1.0-eval-suite-split.md), [v7.0.4](v7.0.4-session-shell-polish.md), [v7.0.3](v7.0.3-productized-subagent-roles.md), [v7.0.2](v7.0.2-single-command-agent-run.md), [v7.0.1](v7.0.1-metadata-narrative-sync.md), [v7.0.0](v7.0.0-second-stable-contract-cut.md) |
| v6 | 2 | second major contract cut plus portfolio maturity evidence | [v6.1.0](v6.1.0-portfolio-maturity.md), [v6.0.0](v6.0.0-major-contract-cut.md) |
| v5 | 16 | first native-tool stable contract cut, trust modes, context intelligence, MCP bridge, release path, prompt/eval/demo polish, v6 prep | [v5.0.0](v5.0.0-first-stable-contract.md), [v5.8.2](v5.8.2-v6-prep-baseline.md), [v5.5.2](v5.5.2-production-docs.md) |
| v4 | 59 | shell-first, provider profiles, first-run usability (v4.14–v4.16), interaction quality (v4.17–v4.18), resume MVP, agentic loop, debug/memory/local git | [v4.18.2](v4.18.2-rollback-safety-regression-fix.md), [v4.18.1](v4.18.1-agent-loop-transparency.md), [v4.18.0](v4.18.0-diff-rendering-per-patch-undo.md), [v4.17.3](v4.17.3-fuzzy-matching.md), [v4.17.2](v4.17.2-live-connectivity.md), [v4.17.0](v4.17.0-streaming-output.md), [v4.16.2](v4.16.2-error-message-rewrite.md), [v4.15.0](v4.15.0-sac-init-front-door.md), [v4.14.0](v4.14.0-provider-profile-ux.md) |
| v3 | 51 | public contracts, providers, MCP, productization, setup, docs and release readiness | [v3.99.1](v3.99.1-promotion-decisions.md), [v3.99.0](v3.99.0-v4-readiness-audit.md), [v3.10.2](v3.10.2-context-budgets-stack-tutorials.md), [v3.0.0](v3.0.0-public-contract-stabilization.md) |
| v2 | 87 | hardening, release tooling, diagnostics, policy presets, sandbox previews, eval fixtures | [v2.9.9](v2.9.9-public-contract-snapshot-tests.md), [v2.8.10](v2.8.10-final-v28-baseline-sync.md), [v2.6.21](v2.6.21-final-signoff.md), [v2.0.0](v2.0.0-real-llm-agent-contract.md) |
| v1 | 17 | local policy-gated execution, approvals, session state, agent loop recovery | [v1.9.5](v1.9.5-agent-recovery.md), [v1.9.2](v1.9.2-agent-run-loop.md), [v1.8.0](v1.8.0-sandbox-execution-mvp.md) |
| v0 | 6 | first ask/edit/apply/rollback demo capabilities | [v0.1.5](v0.1.5-fastapi-demo.md), [v0.1.0](v0.1.0-ask-audit.md) |

## Naming

Version notes use:

```text
v<major>.<minor>.<patch>-<short-feature-name>.md
```

Release tooling expects new completion notes to live in this directory.

## Maintenance

- Add one note per release or patch train.
- Keep current behavior in user-facing docs; keep release archaeology here.
- Prefer linking from [../version_implementation_matrix.md](../version_implementation_matrix.md)
  instead of adding long release-note lists to README.
