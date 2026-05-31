# Feature Edit Tutorial

Materialize:

```bash
sac demo materialize fastapi-health-endpoint
cd examples/demo-workflows/fastapi-health-endpoint
```

Add the feature through the review/apply loop:

```bash
sac edit "Add a /health endpoint that returns {'status': 'ok'}."
sac apply
sac test run --yes
```
