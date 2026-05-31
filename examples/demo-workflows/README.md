# SafeCode Demo Workflows

Use the built-in demo suite to create repeatable seed projects:

```bash
sac demo list
sac demo show fastapi-health-endpoint
sac demo materialize fastapi-health-endpoint
cd examples/demo-workflows/fastapi-health-endpoint
sac edit "Add a /health endpoint that returns {'status': 'ok'}."
sac apply
sac test run --yes
```

The suite currently covers FastAPI, CLI, docs-only, and failing-test repair
workflows.
