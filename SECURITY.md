# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 5.x     | Yes       |
| < 5.0   | No        |

## Reporting a Vulnerability

Please report security vulnerabilities by opening a GitHub issue with the
`security` label, or by contacting the maintainer directly.

Do **not** include exploit details or proof-of-concept code in a public issue.
A maintainer will respond within 7 days with a plan for a fix and coordinated
disclosure.

## Security Model

SafeCode Agent is a local terminal tool. Its security model is documented in
[docs/security/threat-model-v3.6.md](docs/security/threat-model-v3.6.md).

Key invariants:
- Patch writes require explicit user approval before any file is modified.
- Shell commands are policy-gated; high-risk commands are blocked by default.
- Project-local config cannot lower user-level safety policy.
- Secrets are redacted from context before being sent to an LLM provider.
- Audit logs are append-only with a SHA-256 hash chain.
- All writes are checkpointed with rollback support.

The threat model covers prompt injection, path traversal, sandbox escape,
and supply-chain integrity. Semi-annual threat model reviews are scheduled.
