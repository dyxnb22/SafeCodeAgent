# Docs Edit Tutorial

Materialize:

```bash
sac demo materialize docs-safety-note
cd examples/demo-workflows/docs-safety-note
```

Use SafeCode for a documentation-only edit:

```bash
sac edit "Document how to review a SafeCode patch before applying it."
sac apply
sac history
```
