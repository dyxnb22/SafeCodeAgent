# SafeCode Agent Documentation

This index separates the current reading path from historical release records.
Start here when you are unsure which document owns a topic.

## Start Here

- [Golden Demo](../examples/golden-demo/demo/expected-transcript.md): complete bug-to-tested-commit loop (read-only transcript).
- [Portfolio Demo Overview](demo/portfolio-demo.md): the scenario, safety gates, and architecture notes.
- [User Guide](user-guide.md): first-run setup and common daily workflows.
- [Command Reference](reference/commands.md): detailed command reference after the first run.
- [Troubleshooting](troubleshooting.md): diagnostics, blocked commands, rollback, and recovery.
- [Install and Update](install-update.md): local development, pipx, TestPyPI rehearsal, signing, and release checks.
- [Onboarding Tutorials](tutorials/README.md): task-focused and stack-focused walkthroughs.

## Current Product Truth

- [Current Status](current-status.md): current baseline after `v7.1.5`.
- [Version Summary](reference/version-summary.md): short map of major version trains.
- [Release Ledger](release-ledger.md): compact release history used by release tooling.
- [Public Contracts](public-contracts.md): stable and experimental public surfaces.
- [Versioning Policy](versioning-policy.md): patch, minor, major, and contract-churn rules.

## Configuration and Operation

- [Reference Documentation](reference/README.md): grouped reference index for stable-path docs.
- [LLM Providers](providers.md): provider setup, environment variables, retries, streaming, and cost accounting.
- [Context Budgets](context-budgets.md): context-packing limits and budget reporting.
- [Tag + Version Plan Workflow](version-plans/README.md): release planning and ledger workflow.
- [Version Implementation Matrix](version_implementation_matrix.md): detailed implementation ledger and acceptance commands.

## Product and Security References

- [Why SafeCode Agent](why-safecode.md): product rationale, comparison, and safety loop.
- [Security Threat Model](security/threat-model-v3.6.md): personas, risks, and mitigations.

## Historical Records

These documents are useful for archaeology, audits, and release traceability, but
they should not be treated as the current user path.

- [Version Plans](version-plans/README.md): template and workflow for new planning.
- [Planning History](planning-history.md): compact summary of completed roadmaps.

## Maintenance

Run `python3 scripts/check-doc-links.py` from the repository root before large
documentation changes. `tests/test_docs_governance.py` protects this index,
reference entry points, tutorial structure, and release-ledger navigation.
