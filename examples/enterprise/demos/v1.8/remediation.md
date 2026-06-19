# Vulnerability Remediation Demo (v1.8)

## Goal

Show an offline Semgrep finding flowing through the enterprise workflow to a
governed patch proposal, checkpoint, approval-gated apply, revalidation, and
final remediation report.

## Steps

```bash
# 1. Run remediation on the SQL-injection fixture
sac enterprise workflow run \
  --task remediation \
  --input examples/enterprise/fixtures/remediation/sql_injection \
  --root .

# 2. Review the pending approval (workflow pauses before patch apply)
sac enterprise approval list <run_id> --pending --markdown

# 3. Approve and resume to apply the patch and run post-validation
sac enterprise approval decide <run_id> approval-<run_id> --decision approved
sac enterprise workflow resume <run_id>

# 4. Inspect the remediation report and patch artifacts
cat .sac/enterprise/runs/<run_id>/remediation_report.md
cat .sac/enterprise/runs/<run_id>/patch_proposal.json

# 5. Optional: run the remediation eval suite (isolated workspaces)
sac enterprise eval run --suite remediation --root .
sac enterprise eval dashboard --root .
```

## Expected outcomes

- Finding ingested from `finding.json` with vulnerable `app.py` located.
- Policy citation present for SQL-injection fixture.
- Patch proposal parameterizes the SQL query (no raw f-string interpolation).
- Checkpoint created before apply; rollback restores tree on rejection.
- Post-validation passes; final status `succeeded`.
- Rejection path leaves the working tree unchanged and records audit events.

## Rejection walk-through

```bash
sac enterprise approval decide <run_id> approval-<run_id> --decision rejected
sac enterprise workflow resume <run_id>
# Working tree matches pre-patch state; audit chain remains intact.
```
