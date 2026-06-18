# SafeCode Install and Update

## Local Source Checkout

```bash
git pull --ff-only
scripts/test-fast.sh                         # fast local feedback
PYTHONPATH=src python3 -m pytest -q          # full release gate
PYTHONPATH=src python3 -m pytest -q -n auto  # optional parallel full run
python3 scripts/verify-package.py            # packaging inputs and artifacts when build is installed
```

For a clean installation rehearsal:

```bash
python3 -m pip install build                  # once, if the build module is missing
python3 -m build --sdist --wheel
python3 -m pipx install --force .
mkdir -p /tmp/safecode-empty && cd /tmp/safecode-empty && sac --help
```

Also check a plain directory and a git repository:

```bash
tmp=$(mktemp -d)
(cd "$tmp" && sac --help)
(cd "$tmp" && git init && sac --help)
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
scripts/test-fast.sh
PYTHONPATH=src python3 -m pytest -q
python3 scripts/verify-package.py
git add -p                      # stage only version + release-ledger changes
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

## sac run Exit Codes

`sac run` returns these exit codes when a command is not executed:

- `125` — approval required (medium-risk command, no `--yes` or stored approval)
- `126` — policy blocked (high-risk command or disallowed executable)

If your scripts relied on `sac run` returning `1` for all blocked cases, set the
one-cycle opt-out for the migration cycle:

```bash
SAFECODE_RUN_LEGACY_EXIT_CODE=1 sac run "..."
```

This opt-out will be removed in a future version.

## Release Signing

SafeCode release artifacts are signed using a **detached signature** produced by either
`cosign sign-blob` or `gpg --detach-sign --armor` (whichever is available on the release
machine). This is **not** a Sigstore Rekor transparency-log entry; it is a plain detached
signature file placed alongside each wheel/sdist in `dist/`.

To sign during a real publish:

```bash
SAFECODE_PUBLISH=1 sac release publish --no-dry-run --sign
```

The `--sign` flag fails closed if neither `cosign` nor `gpg` is found.
The dry-run step description explicitly names the mechanism:

```
[dry-run] sign: detached signature via cosign (sign-blob) or gpg (--detach-sign --armor)
```

## TestPyPI Rehearsal

Before publishing to PyPI, rehearse the upload against TestPyPI:

```bash
# Dry-run rehearsal (no network, no upload):
sac release publish --repository test-pypi

# Real TestPyPI upload (requires SAFECODE_PUBLISH=1):
SAFECODE_PUBLISH=1 sac release publish --no-dry-run --repository test-pypi

# Install from TestPyPI using pipx:
pipx install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  safecode-agent
```

Production publish to PyPI (still requires `SAFECODE_PUBLISH=1` and a matching git tag):

```bash
SAFECODE_PUBLISH=1 sac release publish --no-dry-run
```

## Install Matrix (v5.5+)

| Method | Command | Notes |
|---|---|---|
| **PyPI (recommended)** | `pipx install safecode-agent` | Requires pipx ≥ 1.0; Python 3.11+ |
| **Offline wheel** | `uv build && pipx install dist/<wheel>` | From source checkout |
| **Source dev** | `git clone … && uv sync` | Full dev environment with tests |

### PyPI Install

```bash
pipx install safecode-agent
sac doctor
```

To upgrade an existing install:

```bash
pipx upgrade safecode-agent
```

### Offline Wheel Install

```bash
git clone <repo>
cd safecode-agent
uv build             # produces dist/safecode_agent-X.Y.Z-py3-none-any.whl
pipx install dist/safecode_agent-X.Y.Z-py3-none-any.whl
```

### Source Dev Install

```bash
git clone <repo>
cd safecode-agent
uv sync
PYTHONPATH=src python3 -m pytest -q
uv run sac doctor
```

## Current Enforcement Boundaries

- Sandbox command execution defaults to Noop. Noop is policy-gated only and is not an OS containment boundary.
- Docker, macOS Seatbelt, and Linux Bubblewrap remain preview until the current host/backend passes:

```bash
sac sandbox executor-preflight docker
sac sandbox executor-preflight seatbelt
sac sandbox executor-preflight bubblewrap
```

- Real execution for preview backends is opt-in and requires both a passing executor preflight record and an explicit env var:
  - Docker: `SAFECODE_SANDBOX_DOCKER=1`
  - macOS Seatbelt: `SAFECODE_SANDBOX_SEATBELT=1`
  - Linux Bubblewrap: `SAFECODE_SANDBOX_BUBBLEWRAP=1`
- `sac doctor` reports promotion state per backend. The default recommendation remains Noop.
- MCP support is currently a SafeCode subprocess JSON shim, not a full MCP JSON-RPC client.
- Subagents currently collect read-only context/result summaries; they are not yet independent LLM investigations.
