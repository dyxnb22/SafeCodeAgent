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

## Current Enforcement Boundaries

- Sandbox command execution currently runs through the Noop backend and Docker preview backend. Docker requires an approved proposal and a reachable Docker daemon. macOS Seatbelt and Linux Bubblewrap remain plan-only/dry-run until their real-backend preview versions.
- MCP support is currently a SafeCode subprocess JSON shim, not a full MCP JSON-RPC client.
- Subagents currently collect read-only context/result summaries; they are not yet independent LLM investigations.
