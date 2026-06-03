# Troubleshooting SafeCode Agent

## Diagnostics First

Before debugging manually, run the built-in diagnostics:

```bash
sac doctor
```

`sac doctor` checks: Python version, project root detection, config file,
approval directory, LLM provider, last session cost, and package version
against PyPI.

For release-related issues:

```bash
sac release preflight
```

---

## Common Issues

### "No pending patch to apply"

**Cause:** `sac apply` was run without a prior `sac edit`, or the pending
patch was already applied or rejected.

**Fix:** Run `sac edit "your task"` first. If the patch was already applied,
check `sac history` or the audit log.

---

### "Command blocked by policy"

**Cause:** The shell command you asked SafeCode to run is classified as
high-risk or is not in the allowed command list for your current policy preset.

**Fix:**
1. Run `sac config policy-audit` to see the effective policy.
2. If you intended to run the command, check that your policy preset allows it:
   `strict` has the fewest allowed commands; `experimental` allows more.
3. High-risk commands are blocked in all presets — this is intentional.

See [README.md](../README.md#policy-presets) for preset descriptions.

---

### "Network access is disabled"

**Cause:** Network access is `false` in all policy presets by default. Real
LLM calls require the network to be enabled.

**Fix:** Add to your user-level config (`~/.sac/config.toml`):

```toml
network_enabled = true
network_allowlist = ["api.openai.com"]
```

Both lines are required. A project-level config cannot enable network access
by itself. See [docs/mvp-user-guide.md](mvp-user-guide.md#model-configuration).

---

### "Approval not found" or "approval expired"

**Cause:** Sandbox approvals are single-use and bound to the project root.
An approval created for one project root is not valid in another.

**Fix:**
- Run `sac sandbox pending` to see pending proposals.
- Run `sac sandbox approve <id>` to create a new approval.
- Approvals live outside the project root; check your `SAFECODE_APPROVAL_DIR`.

---

### "Audit anchor mismatch" or "integrity failure"

**Cause:** The audit log JSONL file has been modified since the last anchor
was written, or the anchor file is missing.

**Fix:**
- Do not manually edit `.sac/logs/events.jsonl`.
- If the log was accidentally modified, the safest recovery is to archive it
  and start a fresh session.
- The anchor lives outside the project root (`SAFECODE_APPROVAL_DIR`).

---

### "Version mismatch between pyproject.toml and safecode.__version__"

**Cause:** The package was installed from a source tree where the version
strings are out of sync.

**Fix:** Run `sac release check` to see the mismatch details. If you are
developing locally, run `sac release bump X.Y.Z` to update both files, then
reinstall with `uv sync`.

---

### LLM returns empty or malformed output

**Cause:** The model returned a response that failed schema validation.
SafeCode will retry once (`RecoverableContractFailure`) and then stop.

**Fix:**
1. Check `sac logs show --level error` for the structured error.
2. Try a different model or check your API key.
3. If using a custom `base_url`, verify the API is OpenAI-compatible.

---

### "sac rollback --last" does nothing

**Cause:** No checkpoint was written before the last apply, or the checkpoint
was already consumed.

**Fix:**
- Checkpoints are written automatically before every `sac apply`. If you
  modified files manually after applying, `sac rollback` only undoes the last
  `sac apply`.
- Use `sac history` to see available checkpoints.

---

## Runtime Logs

For detailed error context:

```bash
sac logs show --limit 20
sac logs show --level error --traceback
```

Runtime logs are structured JSONL at `.sac/logs/runtime.jsonl`. Each entry
includes component, level, message, error type, traceback, and extra metadata.

---

## Getting More Help

- Run `sac --help` for command reference.
- Run `sac <command> --help` for per-command options.
- See [docs/mvp-user-guide.md](mvp-user-guide.md) for a guided walkthrough.
- See [docs/public-contracts.md](public-contracts.md) for stable API contracts.
- File issues at the project repository.
