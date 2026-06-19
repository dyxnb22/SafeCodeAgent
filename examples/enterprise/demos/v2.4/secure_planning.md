# v2.4 Secure Planning Demo

Runs the `secure_planning` workflow against a ticket fixture and produces a
cited plan with alternatives and a revisit trigger.

## Offline verification

```bash
uv run pytest tests/enterprise/workflow/test_secure_planning_offline.py -q
```

## Example fixture

`examples/enterprise/fixtures/ticket_password_reset/ticket.md`

## Expected artifacts

- `plan.md` with policy citations, alternatives, and revisit trigger
- `Report.kind = plan_report` in workflow state
