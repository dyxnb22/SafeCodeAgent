# Live Vulnerability Remediation Demo (v2.2.5)

## Goal

Demonstrate the v2.2 governed remediation path from an offline finding fixture
through patch proposal, human approval, local apply/revalidation, and a single
namespaced branch push plus one remediation PR. The default integration lane uses
recorded HTTP transports.

## Contract gate

```bash
uv run pytest tests/enterprise/integration/test_remediation_v2_2.py -q
```

## Offline recorded replay

```bash
# 1. Run remediation on the SQL-injection fixture (local orchestrator)
sac enterprise workflow run \
  --task remediation \
  --input examples/enterprise/fixtures/remediation/sql_injection \
  --root .

# 2. Approve the pending patch and resume apply + post-validation
sac enterprise approval decide <run_id> approval-<run_id> --decision approved
sac enterprise workflow resume <run_id>

# 3. Replay governed branch/PR integration checks (recorded transports)
uv run pytest tests/enterprise/integration/test_remediation_v2_2.py -q
```

## Live sample-repo walk-through (operator supplied credentials)

```bash
export SAC_ENTERPRISE_GITHUB_APP_ID="<app-id>"
export SAC_ENTERPRISE_GITHUB_INSTALLATION_ID="<installation-id>"
export SAC_ENTERPRISE_GITHUB_PRIVATE_KEY_PEM="$(cat /secure/path/key.pem)"

# After local patch validation succeeds, approve branch push and PR create.
# The platform opens one `safecode/<run_id>` branch and one remediation PR.
```

## Expected outcomes

- Finding ingested from `finding.json`; patch parameterizes the SQL query.
- Approval-gated apply creates a checkpoint and passes post-validation.
- Approved recorded replay pushes one namespaced branch and opens one PR.
- Changed patch digests, protected-branch targets, and duplicate CI callback
  deliveries fail closed without a second remote write.
- Merge and deployment remain out of scope.

## Tear-down

- Close or delete the sandbox remediation PR through a separately approved
  compensating action.
- Roll back local files from checkpoint if the run did not complete.
