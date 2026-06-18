# Planning History

This page keeps the compact planning record after completed roadmap files have
been removed from `docs/version-plans/`.

## Completed Roadmaps

| Roadmap | Outcome | Canonical History |
| --- | --- | --- |
| v7.0.x agent productization follow-up | v7.0.1 metadata/narrative sync; v7.0.2 single-command agent flow; v7.0.3 productized subagent roles; v7.0.4 shell/session polish and docs governance alignment. | [release ledger](release-ledger.md), [version summary](reference/version-summary.md) |
| v6.29 to v7.0 next roadmap | AgentLoop refactor, workspace memory, native-tool coverage, dynamic replanning, context back-pressure, symbol discovery, and v7 stable contract cut. | [release ledger](release-ledger.md), [implementation matrix](version_implementation_matrix.md) |
| post-v4.16 shell UX train | Streaming output, shell polish, live connectivity, fuzzy matching, per-patch undo, agent-loop transparency, and safety regression fix. | [release ledger](release-ledger.md), [implementation matrix](version_implementation_matrix.md) |
| post-v4.14 usability train | Provider profiles, model aliases, `sac init`, session model switching, keychain credentials, bare `sac` shell, config migration, and error rewrites. | [release ledger](release-ledger.md), [implementation matrix](version_implementation_matrix.md) |

## Maintenance Rule

Keep detailed acceptance criteria in an active plan only while the work is open.
After completion, summarize the outcome here, add or update the matching
[release-ledger.md](release-ledger.md) entry, and leave deep implementation
details to [version_implementation_matrix.md](version_implementation_matrix.md).
