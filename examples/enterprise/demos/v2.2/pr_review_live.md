# Live PR Security Review Demo (v2.2.5)

## Goal

Demonstrate the v2.2 governed PR review path from a signed GitHub webhook
through report generation, human approval, and a single governed comment write.
The default integration lane is fully offline with recorded HTTP transports.

## Contract gate

```bash
uv run pytest tests/enterprise/integration/test_pr_review_v2_2.py -q -m "not live_github"
```

## Offline recorded replay

```bash
# 1. Start the local Team Server profile (webhook secret + GitHub App settings)
./scripts/run-enterprise-dev.sh

# 2. Replay the offline integration suite (recorded transports; no network)
uv run pytest tests/enterprise/integration/test_pr_review_v2_2.py -q -m "not live_github"
```

## Live sample-repo walk-through (operator supplied credentials)

```bash
export SAC_ENTERPRISE_GITHUB_APP_ID="<app-id>"
export SAC_ENTERPRISE_GITHUB_INSTALLATION_ID="<installation-id>"
export SAC_ENTERPRISE_GITHUB_PRIVATE_KEY_PEM="$(cat /secure/path/key.pem)"
export SAC_ENTERPRISE_GITHUB_WEBHOOK_SECRET="<webhook-secret>"

# Register the webhook on a forked sample repository, then open a PR with the
# SQL-injection fixture diff. Approve the pending comment in the inbox.

uv run pytest tests/enterprise/integration/test_pr_review_v2_2.py -q -m live_github
```

## Expected outcomes

- Signed webhook delivery queues exactly one `pr_review` run.
- Worker pauses at `approval_gate` with a cited high-risk report.
- Approved resume posts one PR comment through a single-use grant.
- Injection-bearing comment bodies, denied repositories, and CI callback commit
  mismatches produce no GitHub write.
- Tokens and private key material never appear in traces, evidence, or test output.

## Tear-down

- Revoke the webhook on the sample repository.
- Discard disposable `.sac` state and Compose volumes (`docker compose down -v`).
