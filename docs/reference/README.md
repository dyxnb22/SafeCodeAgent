# Reference Documentation

These documents remain at the top level because tests and release tooling use
their stable paths. This page groups them as reference material.

## Contracts and Policy

- [Command Reference](commands.md): command details after the first-run guide.
- [Version Summary](version-summary.md): short map of major version trains.
- [Public Contracts](../public-contracts.md): stable and experimental public surfaces.
- [Versioning Policy](../versioning-policy.md): patch, minor, major, and contract-churn rules.
- [Version Implementation Matrix](../version_implementation_matrix.md): detailed implementation ledger and acceptance commands.
- [Tag + Version Plan Workflow](../version-plans/README.md): release planning and version-note workflow.

## Configuration and Operations

- [LLM Providers](../providers.md): provider setup, environment variables, retries, streaming, and cost accounting.
- [Context Budgets](../context-budgets.md): context-packing limits and budget reporting.
- [Install and Update](../install-update.md): local development, pipx, TestPyPI rehearsal, signing, and release checks.

## Product and Security

- [Why SafeCode Agent](../why-safecode.md): product rationale, comparison, and safety loop.
- [Troubleshooting](../troubleshooting.md): diagnostics, blocked commands, rollback, and recovery.
- [Threat Model](../security/threat-model-v3.6.md): personas, risks, and mitigations.

## Maintenance

Use `python3 scripts/check-doc-links.py` to check relative documentation links.
The pytest coverage for this structure lives in `tests/test_docs_governance.py`.
