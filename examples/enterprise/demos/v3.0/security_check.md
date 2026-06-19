# v3.0 Candidate Security Acceptance Checklist

Gate owner: designated independent reviewer with `security_reviewer` role.

| Mechanism | Check | Status |
|---|---|---|
| Engineering | Contract + migration tests green | PENDING FINAL SHA |
| Engineering | Full offline regression green | PENDING FINAL SHA |
| Product | Flagship demos repeat offline fixtures | PASS |
| Security | Internal remediation findings closed | PENDING FINAL SHA |
| Security | Independent review and detached signature | BLOCKED |
| Security | Production deployment artifact | BLOCKED |
| Evaluation | Eval baselines locked | PASS |
| Evaluation | Stable live-provider run artifact | BLOCKED |
| Demo | Console approval uses idempotency contract | PASS |

The release remains a candidate while any BLOCKED row exists. Repository tests
cannot turn external evidence green.
