# SafeCode Agent Threat Model v3.6

## Scope

This document covers the SafeCode Agent threat model as of v3.6. It describes
assumptions, trust boundaries, attacker personas, and per-surface mitigations.
It should be reviewed semi-annually, or whenever a new execution surface or
contract promotion is introduced.

**Next scheduled review:** 2026-12-01 (or at v4.0, whichever is earlier).

---

## Assumptions

- The local operating system and Python interpreter are trusted.
- The human operator interacting with `sac` commands is the legitimate user.
- Files under `.sac/` other than project-local config are semi-trusted
  (written by `sac`, not user-editable workflow).
- Network access is disabled by default; all outbound paths require explicit
  opt-in and policy checks.

---

## Personas and Threat Vectors

### Local User

**Threat:** A local user with shell access to the project could attempt to read
audit logs, forge approval files, or manipulate `.sac/` state directly.

**Mitigations:**
- Approval stores and audit anchors live outside the project root
  (`SAFECODE_APPROVAL_DIR`, not inside the repo).
- Audit events carry a SHA-256 hash chain; tampering with the JSONL log
  invalidates the anchor verification.
- `sac release preflight` checks anchor and metadata consistency.
- All user-level safety knobs (`block_high_risk`, `restrict_to_project_root`,
  `network_enabled`) require user-level configuration to change; project-local
  config cannot lower them.

---

### Malicious Repo

**Threat:** A repository checked out by the user could contain crafted files
designed to exfiltrate secrets through context collection, or craft filenames
that escape project root boundaries.

**Mitigations:**
- `FileIndexer` skips secret-like filenames (`.env*`, `*token*`, `*secret*`,
  key files, `*credential*`) before any content is read.
- Context collection enforces byte budget limits; oversized files are truncated.
- `redact_secrets()` is applied to context before it is sent to the LLM.
- All file writes are constrained to the project root via `FilesystemBoundary`.
- Shell commands run through argv execution (`shell=False`), not shell strings;
  repo-provided data never reaches a shell interpreter directly.

---

### Malicious Project Config

**Threat:** A `.sac/config.toml` checked into a repository could attempt to
lower safety policy (e.g., disable `block_high_risk`, enable network access,
change the LLM provider to an attacker-controlled endpoint).

**Mitigations:**
- Config merges use a strictness-wins rule: `_stricter_policy()` always prefers
  the safer value when project config conflicts with user config.
- `sandbox.restrict_to_project_root` cannot be disabled by project config.
- `sandbox.network_enabled` cannot be enabled by project config when user
  config disables it.
- An unknown project policy name is treated as `balanced` (conservative),
  never as `experimental` or lower.
- LLM provider and base URL can only be set by user-level config; project
  config cannot redirect API traffic.
- `sac config policy-audit` audits effective policy knobs and reports
  unexpected values.

---

### Malicious MCP Server

**Threat:** A locally configured MCP server binary could attempt to: return
crafted JSON to influence tool classification, inject content into error
messages that surfaces caller-controlled data, or execute write operations
without approval.

**Mitigations:**
- Tool classification is determined statically by the SafeCode schema layer;
  a server-supplied `"classification"` field in JSON responses is ignored.
- MCP stdio transport enforces a maximum output size (`max_output_bytes`);
  oversized responses fail closed.
- `call_args` content is never copied into error text.
- Write-classified and unknown-classified tools are blocked in the read-only
  runner; only `read`-classified tools can execute without a separate proposal.
- MCP write operations require an explicit proposal and user approval before
  execution; approved proposals are single-use.
- All MCP surfaces remain experimental and are not wired into the default
  agent loop without explicit opt-in.

---

### Malicious Model Output

**Threat:** A compromised or jailbroken LLM could return output designed to:
propose patches that escape the project root, inject shell commands into patch
content, or exploit the agent loop to approve unapproved operations.

**Mitigations:**
- `validate_provider_json()` validates all LLM responses against typed schemas;
  soft failures return `RecoverableContractFailure` rather than crashing or
  executing.
- Patch proposals are parsed, validated by `PatchValidator`, and shown to the
  user as a diff before any write occurs.
- Tool intents are classified and routed by `ToolIntentRouter` using static
  metadata from the `ToolRegistry`; LLM output cannot override approval flags.
- `ToolCallAdapter.validate()` enforces required args and type checks before
  any tool action proceeds.
- The `FilesystemBoundary` blocks writes outside the project root even if the
  model proposes them.
- Checkpoint is written before every patch apply; rollback is always available.

---

### Network and Provider Risk

**Threat:** An attacker controlling the LLM provider endpoint (man-in-the-middle,
rogue API key, misconfigured `base_url`) could return adversarial responses or
exfiltrate prompt content.

**Mitigations:**
- Network access is disabled by default across all policy presets.
- Real LLM mode requires explicit user-level `network_enabled = true` and an
  `network_allowlist` entry for the provider host.
- A project-local config cannot enable network access by itself; both user-level
  and project-level policies must agree.
- The provider base URL is a user-level config value; project config cannot
  redirect it.
- `retry_call()` honors Retry-After headers but does not log prompt or response
  content in retry warnings.
- The OTel exporter is disabled by default; when enabled, endpoint URLs are
  never included in error text.
- The PyPI update-check (`Doctor._update_check_diagnostic`) fetches only from
  the PyPI JSON API; no telemetry is sent; the fetch never raises; offline
  → `None` (SKIP).

---

### Audit and Approval Trust Boundaries

**Threat:** An attacker with project-root write access could forge audit events,
replay consumed approvals, or replace anchors to cover up unauthorized writes.

**Mitigations:**
- Audit events are appended to an append-only JSONL log; each carries a
  SHA-256 hash over its own content (with `event_hash` nulled during hashing)
  and the previous event's hash, forming a chain.
- The `AuditAnchorStore` writes `line_count` and the latest hash to a path
  outside the project root; a non-empty log without a valid anchor is an
  integrity failure.
- Sandbox approvals are single-use: `claim_for_execution()` is atomic; a
  claimed approval cannot be replayed.
- Hook approvals are bound to project root hash, user, command, and schema
  version; an approval valid in one project root is invalid in another.
- Approval directories live outside the project root and are not project-config
  settable.

---

### Sandbox Limitations

**Threat:** Sandbox backends (Docker, macOS Seatbelt, Linux Bubblewrap) may
not provide complete containment on all OS/kernel configurations.

**Mitigations:**
- Each backend requires an explicit proposal, user approval, preflight check,
  and preview hash verification before execution.
- `--privileged` is never passed to Docker; `--network none` is the default.
- macOS Seatbelt profiles enforce no network outbound by default.
- Linux Bubblewrap enforces `--unshare-net` by default.
- Sensitive paths (`.ssh`, `.env`, `.aws`, `credentials`, `token`, `secret`)
  are rejected as writable targets by all three backends.
- `shell=False` is enforced in all `subprocess.run()` calls in all backends.
- The Noop backend executes commands through SafeCode logical boundaries
  (policy, approval, audit) without OS-level containment; it is not a security
  boundary, only a gating mechanism.
- Backend unavailability (daemon not running, binary not found) always fails
  closed — it never degrades silently to an unconstrained execution path.
- Real Docker, macOS Seatbelt, and Linux Bubblewrap execution requires both a
  passing current-host executor preflight and explicit env opt-in:
  `SAFECODE_SANDBOX_DOCKER=1`, `SAFECODE_SANDBOX_SEATBELT=1`, or
  `SAFECODE_SANDBOX_BUBBLEWRAP=1`.
- `sac sandbox executor-preflight <backend>` records backend promotion state;
  `sac doctor` reports each backend as policy-gated, preview, or opt-in real
  execution. The default recommendation remains Noop.

---

### Telemetry and Update-Check Guarantees

**Threat:** An update-check or telemetry call could exfiltrate session content,
project paths, or user identity without consent.

**Mitigations:**
- The `Doctor` update-check (`_fetch_latest_pypi_version`) sends only an HTTPS
  GET to `https://pypi.org/pypi/safecode-agent/json`. No user data, project
  paths, session IDs, or prompt content is included.
- The OTel exporter (`OtelExporter`) is disabled by default; it requires the
  `SAFECODE_OTEL_EXPORTER` environment variable to be set.
- When the OTel exporter is enabled, the endpoint URL is user-configured and
  never included in error messages.
- OTel packages are optional; if not installed, a `RuntimeWarning` is emitted
  and the exporter disables itself.
- No telemetry is emitted during test runs.
- There is no background process, daemon, or persistent network connection.

---

---

### Release Artifact Integrity

**Threat:** A compromised distribution artifact (wheel or sdist) could silently
replace the legitimate release on PyPI.

**Mitigations:**
- Release artifacts are signed with a **detached signature** using either
  `cosign sign-blob` or `gpg --detach-sign --armor`. This is not a Sigstore
  Rekor transparency-log entry; it is a per-artifact `.sig`/`.asc` file placed
  alongside the artifact in `dist/`.
- Real publish requires `SAFECODE_PUBLISH=1`, a clean matching git tag at HEAD,
  and version consistency between `pyproject.toml` and the runtime version.
- `sac release publish --sign` fails closed if no signing tool is found.
- The `--sign` flag documents its actual mechanism in the dry-run step list
  (`detached signature via cosign or gpg`), not a Sigstore transparency log.
- TestPyPI rehearsal (`--repository test-pypi`) exercises the upload path
  without touching the production index.

---

## v4.x Shell-First Addendum (v4.1–v4.8)

The v4.x train added the following surfaces. All remain EXPERIMENTAL and do not
change the fundamental threat model described above. No new trust boundaries were
introduced and no existing safety gate was weakened.

**New experimental surfaces and their threat-model implications:**

| Surface | Threat-model note |
|---|---|
| `sac task` / `.sac/tasks/` | Task sidecars are local files under `sac_dir`; they are redacted on read paths; task IDs are short slugs, not user-controlled paths; `task_id` stuffed into audit metadata does not change the audit event field set. |
| `sac status` | Read-only; never writes audit events. |
| `sac profile` / `.sac/project_profile.json` | Profile detection never executes project commands; user overrides always win; project profile cannot lower user-level policy. |
| `sac resume` | Passive; never auto-runs `edit`, `fix`, `apply`, or a shell command; always prints redacted summary only. |
| `sac commit` / `sac branch new` | Local git only; no push, no remote operations; dirty-tree guard refuses unrelated changes; `--force-uncommit` requires explicit opt-in and emits an audit event. |
| `sac memory` / `.sac/memory/` | Writes reject obvious secrets; reads are redacted; pinned files still pass through ignore, sensitive-file, binary, and project-root gates; memory cannot enable network or lower policy. |
| `sac debug last-failure` / `sac audit query` | Read-only; never executes project commands; output is redacted. |
| `sac debug bundle` | Writes a single tar.gz containing SafeCode metadata only; excludes project source code; refuses overwrite without `--force`; capped at 5 MiB. |
| `sac smoke shell-first` | Test-only surface; uses mock provider; no real LLM calls; hidden from root help; all scenarios run in temporary directories. |
| `sac fix --watch` | Never auto-applies patches; every proposal remains pending until explicit `sac apply`; failure categories are informational and do not bypass policy. |

The v4.x train is now complete as of v4.8.2. The next scheduled threat-model
review is the semi-annual review below.

---

## Review Cadence

This document should be reviewed:

1. **Semi-annually** — scheduled for 2026-12-01.
2. **On any new execution surface** — e.g., when MCP write execution is promoted
   from experimental to stable, or when a new sandbox backend is added.
3. **On any trust boundary change** — e.g., a change to approval store location
   policy, audit chain format, or config precedence rules.

Reviewers should update this file and add a dated entry to the review log below.

### Review Log

| Date | Version | Reviewer | Notes |
|------|---------|----------|-------|
| 2026-06-03 | v3.6.4 | SafeCode team | Initial v3.6 threat model |
