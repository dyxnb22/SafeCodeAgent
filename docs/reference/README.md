# Reference Documentation

These documents remain at the top level because tests and release tooling use
their stable paths. This page groups them as reference material.

## Contracts and Policy

- [Command Reference](commands.md): command details after the first-run guide.
- [Version Summary](version-summary.md): short map of major version trains.
- [Public Contracts](../public-contracts.md): stable and experimental public surfaces.
- [Versioning Policy](../versioning-policy.md): patch, minor, major, and contract-churn rules.
- [Version Implementation Matrix](../version_implementation_matrix.md): detailed implementation ledger and acceptance commands.
- [Tag + Version Plan Workflow](../version_skill_workflow.md): release planning and version-note workflow.

## Configuration and Operations

- [LLM Providers](../providers.md): provider setup, environment variables, retries, streaming, and cost accounting.
- [Context Budgets](../context-budgets.md): context-packing limits and budget reporting.
- [Install and Update](../install-update.md): local development, pipx, TestPyPI rehearsal, signing, and release checks.

## Product and Security

- [Why SafeCode Agent](../why-safecode.md): product rationale and safety loop.
- [Comparison](../compare.md): comparison with raw LLM usage and autonomous coding agents.
- [Troubleshooting](../troubleshooting.md): diagnostics, blocked commands, rollback, and recovery.
- [Product Commercialization Roadmap](../product-commercialization-roadmap.md): architecture reference, not the active roadmap.
- [Threat Model](../security/threat-model-v3.6.md): personas, risks, and mitigations.
- [Product Security Review v2.6](../security/product-security-review-v2.6.md): historical security review kept under security.

## Maintenance

Use `python3 scripts/check-doc-links.py` to check relative documentation links.
The pytest coverage for this structure lives in `tests/test_docs_governance.py`.
