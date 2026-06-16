# SafeCode Agent Documentation

This index separates the current reading path from historical release records.
Start here when you are unsure which document owns a topic.

## Start Here

- [Golden Demo](../examples/golden-demo/demo/expected-transcript.md): complete bug-to-tested-commit loop (read-only transcript).
- [Portfolio Demo Overview](demo/portfolio-demo.md): the scenario, safety gates, and architecture notes.
- [MVP User Guide](mvp-user-guide.md): first-run setup and common daily workflows.
- [Command Reference](reference/commands.md): detailed command reference after the first run.
- [Troubleshooting](troubleshooting.md): diagnostics, blocked commands, rollback, and recovery.
- [Install and Update](install-update.md): local development, pipx, TestPyPI rehearsal, signing, and release checks.
- [Onboarding Tutorials](tutorials/README.md): task-focused and stack-focused walkthroughs.

## Current Product Truth

- [Final Status and Roadmap](project-final-status-and-roadmap.md): current baseline after `v6.1.0`.
- [Version Summary](reference/version-summary.md): short map of major version trains.
- [Public Contracts](public-contracts.md): stable and experimental public surfaces.
- [Versioning Policy](versioning-policy.md): patch, minor, major, and contract-churn rules.

## Configuration and Operation

- [Reference Documentation](reference/README.md): grouped reference index for stable-path docs.
- [LLM Providers](providers.md): provider setup, environment variables, retries, streaming, and cost accounting.
- [Context Budgets](context-budgets.md): context-packing limits and budget reporting.
- [Tag + Version Plan Workflow](version_skill_workflow.md): release planning and version-note workflow.
- [Version Implementation Matrix](version_implementation_matrix.md): detailed implementation ledger and acceptance commands.

## Product and Security References

- [Why SafeCode Agent](why-safecode.md): product rationale and safety loop.
- [Comparison](compare.md): comparison with raw LLM usage and autonomous coding agents.
- [Product Commercialization Roadmap](product-commercialization-roadmap.md): architecture reference, not the active roadmap.
- [Security Threat Model](security/threat-model-v3.6.md): personas, risks, and mitigations.
- [Product Security Review v2.6](security/product-security-review-v2.6.md): historical security review.

## Historical Records

These documents are useful for archaeology, audits, and release traceability, but
they should not be treated as the current user path.

- [Documentation Archive](archive/README.md): historical audits, roadmaps, and review follow-ups.
- [Version Notes](version-notes/README.md): release-by-release completion notes.
- [Version Plans](version-plans/README.md): completed and active planning documents.
- [Post-v4.12 Consolidation Audit](post-v4.12-consolidation-audit.md): historical documentation consolidation findings.

## Maintenance

Run `python3 scripts/check-doc-links.py` from the repository root before large
documentation changes. `tests/test_docs_governance.py` protects this index,
archive/reference entry points, tutorial structure, and version-note navigation.
