# Security Policy

## Release Status

The repository contains a `v3.0` candidate, not an approved Enterprise GA
release. Independent security sign-off, production-like deployment evidence,
and stable live-provider evidence remain open external gates.

## Reporting a Vulnerability

Report vulnerabilities privately to the maintainer or through the repository
host's private security-advisory channel. Do not place exploit details,
credentials, customer data, or proof-of-concept code in a public issue.

Include the affected commit or version, impacted surface, reproduction
conditions, and any known mitigation. The maintainer should acknowledge the
report, coordinate remediation, and disclose only after a safe fix is available.

## Security Model

The maintained threat model is
[enterprise-docs/security/threat-model-v2.5.md](enterprise-docs/security/threat-model-v2.5.md).
Current candidate findings and unresolved external gates are documented in:

- [security review](enterprise-docs/security/security-review-v3.0.md)
- [external GA gates](enterprise-docs/security/external-gates.md)

Core invariants:

- Model output is never execution authority.
- Writes, commands, MCP operations, and connector mutations pass deterministic
  policy and approval gates.
- Unknown capabilities and network access are denied by default.
- Project configuration cannot weaken user or organization policy.
- Retrieved and external content is untrusted and permission filtered.
- Secrets are redacted before model use, persistence, logging, or export.
- Audit events are append-only and hash chained.
- Mutating workflows preserve rollback or audited compensation.
- Tenant identity and approval bindings are validated at every persistence and
  execution boundary.
