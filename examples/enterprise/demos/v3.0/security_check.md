# v3.0 GA security acceptance checklist

Gate owner: designated reviewer with `security_reviewer` role.

| Mechanism | Check | Status |
|-----------|-------|--------|
| Engineering | Contract + migration tests green | PASS |
| Engineering | Full offline regression at GA SHA | PASS |
| Product | Flagship demos reference offline fixtures | PASS |
| Security | `enterprise-docs/security/security-review-v3.0.md` filed | PASS |
| Security | No open high/critical findings in review table | PASS |
| Security | Threat model v2.5 cross-reference present | PASS |
| Evaluation | Eval baselines locked; ratchet tests green | PASS |
| Demo | Console approval demo uses idempotency header contract | PASS |

## Verification commands

```bash
uv run pytest tests/enterprise/security/test_ga_security_review_contract.py -q
uv run pytest tests/enterprise/contracts/test_public_contract_v3_0.py -q
uv run pytest tests/enterprise/contracts/test_migration_v2_rc_to_v3_0.py -q
```

## Evidence paths

- Security review: `enterprise-docs/security/security-review-v3.0.md`
- Threat model: `enterprise-docs/security/threat-model-v2.5.md`
- Deployment evidence: `examples/enterprise/demos/v3.0/deployment_evidence.md`
