# SafeCode Install and Update

## Local Source Checkout

```bash
git pull --ff-only
PYTHONPATH=src python3 -m pytest -q
```

## First Setup

```bash
sac setup --yes
sac doctor
sac version
```

## Approval Directories

`sac setup` writes `.sac/setup.env` with:

```bash
SAFECODE_APPROVAL_DIR="..."
SAFECODE_SANDBOX_APPROVAL_DIR="..."
```

Use external approval directories rather than project-local approval stores.

## Common Checks

- `sac doctor` verifies Python, uv, project root, config, `.sac/`, and approval env status.
- `sac version` shows the current package version and a source-checkout update hint.
