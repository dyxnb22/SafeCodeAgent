# SafeCode Onboarding Tutorials

Start with one focused built-in workflow:

| Goal | Materialize | Then run |
| --- | --- | --- |
| Bug fix | `sac demo materialize failing-test-repair` | `sac test run --yes`; `sac edit "Fix the calculator add function so the existing failing test passes."`; `sac apply`; `sac test run --yes` |
| Feature edit | `sac demo materialize fastapi-health-endpoint` | `sac edit "Add a /health endpoint that returns {'status': 'ok'}."`; `sac apply`; `sac test run --yes` |
| Docs edit | `sac demo materialize docs-safety-note` | `sac edit "Document how to review a SafeCode patch before applying it."`; `sac apply`; `sac history` |
| Safe shell task | `sac demo materialize safe-shell-status` | `sac run "git status"`; `sac history` |

Each workflow materializes into `examples/demo-workflows/`. Change into the
printed directory before running the follow-up commands.

For stack and end-to-end walkthroughs:

- [Stack First Hour](stack-first-hour.md): shared Python, TypeScript, Go, and local-project workflow.
- [AI Shell: First Hour](ai-shell-first-hour.md)
- [Agent Run: First Hour](agent-run-first-hour.md)
- [From Task to Tested Commit](from-task-to-tested-commit.md)

Before running a tutorial in a fresh checkout, initialize SafeCode:

```bash
sac setup --yes
sac doctor
```
