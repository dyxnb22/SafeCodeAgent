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

To choose a policy preset at setup time:

```bash
sac setup --policy strict       # highest safety
sac setup --policy balanced     # default (same as --yes)
sac setup --policy experimental # widest allowed commands
```

Canonical policy names: `strict`, `balanced`, `experimental`.
Legacy aliases `normal` (= `balanced`) and `learning` (= `experimental`) are also accepted.

An unknown `SAFECODE_POLICY` env var value issues a `UserWarning` and is silently
ignored — the effective policy stays unchanged.  An unknown project-config policy
name cannot override a known user-level policy.

## Approval Directories

`sac setup` writes `.sac/setup.env` with:

```bash
SAFECODE_APPROVAL_DIR="..."
SAFECODE_SANDBOX_APPROVAL_DIR="..."
```

Use external approval directories rather than project-local approval stores.

## Common Checks

- `sac doctor` verifies Python, uv, project root, config, `.sac/`, and approval env status.
- `sac doctor --release` adds tag/docs/preflight diagnostics for release preparation.
- `sac version` shows the current package version and a source-checkout update hint.

## Release Flow

Recommended main path for each release:

```bash
sac release bump X.Y.Z         # update canonical version files; does not commit or tag
PYTHONPATH=src python3 -m pytest -q
git add -p                      # stage only version + version-note changes
git commit -m "Implement vX.Y.Z <summary>"
git tag -a vX.Y.Z -m "vX.Y.Z <summary>"
sac release preflight          # aggregate local gate: check, smoke, metadata, docs, versions governance
sac release changelog --recent 5   # optional: preview the changelog
sac release sync-versions-json     # if versions.json is stale after tagging
git describe --exact-match --tags HEAD
```

The tag version must match `pyproject.toml` and `safecode.__version__`; do not
create or move a release tag while the package still reports an older version.

These internal helpers are hidden from `sac release --help` but remain callable for
troubleshooting and compatibility:

```bash
sac release check              # [advanced] version consistency and working-tree state
sac release smoke              # [advanced] fast smoke test (subset of preflight)
sac release meta               # [advanced] metadata index: version, tag, notes, baseline
sac release checklist vX.Y.Z   # [advanced] planning helper — not a release gate
sac release signoff            # [internal] deprecated; use sac release preflight instead
```

## Current Enforcement Boundaries

- Sandbox command execution currently runs through Noop plus Docker, macOS Seatbelt, and Linux Bubblewrap preview backends. Docker requires a reachable daemon, macOS Seatbelt requires `sandbox-exec`, and Linux Bubblewrap requires `bwrap`.
- MCP support is currently a SafeCode subprocess JSON shim, not a full MCP JSON-RPC client.
- Subagents currently collect read-only context/result summaries; they are not yet independent LLM investigations.
