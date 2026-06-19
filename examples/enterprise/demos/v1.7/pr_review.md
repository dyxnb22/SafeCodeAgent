# PR Security Review Demo (v1.7)

## Goal

Show an offline PR fixture flowing through the enterprise workflow to a
risk-ranked, cited report and optional gated comment write.

## Steps

```bash
# 1. Run PR review on the SQL-injection fixture
sac enterprise workflow run \
  --task pr_review \
  --input examples/enterprise/fixtures/pr_sql_injection \
  --root .

# 2. Inspect the generated report (after approval interrupt, resume or read checkpoint artifact)
cat .sac/enterprise/runs/<run_id>/report.md

# 3. Review pending approval for high-risk runs
sac enterprise approval list <run_id> --pending --markdown

# 4. Optional: run the pr_review eval suite
sac enterprise eval run --suite pr_review --root .
sac enterprise eval dashboard --root .
```

## Expected outcomes

- Risk tier `high` for the SQL-injection fixture.
- At least one policy citation and one code citation in state.
- Draft comment written under `.sac/enterprise/runs/<run_id>/draft_comment.md`.
- Live `pr_comment_post` remains blocked until explicit human approval.
