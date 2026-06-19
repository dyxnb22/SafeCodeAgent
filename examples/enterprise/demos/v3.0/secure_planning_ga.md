# GA Secure Planning Demo (v3.0.4)

Demonstrate governed secure planning introduced in v2.4 under GA contracts.

## Contract gate

```bash
uv run pytest tests/enterprise/workflow/test_secure_planning_offline.py -q
uv run pytest tests/enterprise/contracts/test_public_contract_v3_0.py -q
```

## Offline workflow

```bash
sac enterprise workflow run --task secure_planning --input examples/enterprise/fixtures/prompt_injection/change_policy/doc.md --root .
```

## Expected outcomes

- Retrieved policy content treated as untrusted data.
- Plan actions remain proposals until approval gates pass.
