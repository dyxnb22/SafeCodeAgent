# SafeCode Agent — Product-Level Comprehensive Audit (read-only)

Repository state observed: pyproject `2.6.21`, runtime `2.6.21`, `git describe --exact-match HEAD = v2.6.21`. `.claude/versions.json.current_implemented_tag = v2.5.4` (stale — see §8). Working tree clean.

---

## 1. Current Product Positioning

**What this repo is actually becoming.** SafeCode Agent is a *safety-first local edit/run loop* with a strong, evidence-bearing security substrate (diff review, checkpoints, hash-chained audit log, command policy, sandbox planning + opt-in real backends, hook approval store, MCP shim, eval/replay). The most distinctive and product-shaped part of the codebase is actually the **safety substrate**, not the agent. The user-facing CLI surface (`sac ask/edit/apply/rollback`) is a thin demo over that substrate. The interactive `AgentLoop` exists and produces pending patches, but it is still mostly mock-driven (`MockLLMClient.choose_tool` returns calculator/scripted intents — `src/safecode/llm/mock.py` and `loop.py:497-502`).

**Best target user.** A security-curious individual developer or a teaching/research context where the value is *"learn how a coding agent enforces safety boundaries"* — not a daily coding-driver. The exhaustive v1.5.x security branches and the `tests/test_*_security_evals.py` suite (8+ files) are the product's actual strength.

**Differentiation vs Claude Code / Codex / Cursor / Aider.** SafeCode does not currently compete on coding quality, model orchestration, IDE integration, or task autonomy. It competes on *visible safety primitives*: per-tool policy decisions, preview hashes, audit anchoring, claim-based single-use sandbox approvals, redaction. None of the named competitors expose these as inspectable structured objects. If positioned as "an open reference implementation of a hardened local coding-agent runtime / agent-security teaching project," the positioning is clear and defensible. If positioned as "a Claude Code alternative," it is not competitive.

**Conceptual confusion in the current surface.** Yes, real:
- `productization-roadmap-to-claude-code.md` frames the project as a "Claude Code-like runtime," but the v2.6.x work that was actually done (17 hardening releases) is *release tooling*, not Claude Code parity work.
- `sac doctor` now does environment checks AND release diagnostics (`doctor.py:46-79`); the same release flow appears in `sac release check/smoke/meta/preflight/signoff` plus `sac config policy-audit`. The product has five overlapping framings of "is this repo OK to release."
- "Sandbox execute" with Noop backend in v1.8.0+ is just `ShellRunner.run(cmd, approved=True)` with no OS containment (`sandbox/execution.py:881-883`), but is marketed under the sandbox CLI group. Honesty was added in v2.3.5 to flag this, but the panel text in `cli_sandbox.py:33-41` still calls it "Execution Scope (v2.4.x)" and the entire panel is frozen at "v2.4.2 Linux Bubblewrap Sandbox Preview" two versions later.

---

## 2. Current Feature Completeness

### Fairly mature / product-shaped
| Area | Evidence | Why mature |
|---|---|---|
| Patch propose / preview / apply / rollback | `agent/orchestrator.py`, `patch/applier.py`, `checkpoint/manager.py`, `tests/test_patch_apply.py`, `test_checkpoint.py` | End-to-end loop is real, transactional, journaled. v1.5.9 `apply_metadata_preimage` and v1.5.19 `apply_symlink_race_guard` show real hardening. |
| Command policy + shell runner | `policy/commands.py`, `shell/runner.py`, `tests/test_security_hardening.py` | Wide allowlist/denylist coverage (git -c, git -C, python -m, node -e, npx/pip3/uv pip, git env injection, etc.). |
| Audit log with hash chain + external anchor | `audit/logger.py`, `audit/anchor.py`, `tests/test_audit_log.py` | Real tamper detection; anchor moved outside project root in v1.5.17. |
| Hook approval store (user-level, bound) | `hooks/approvals.py:128-145` | Approvals bound to user, command hash, policy version, config hash. Solid design. |
| Context redaction | `context/redactor.py`, `tests/test_security_hardening.py` | GitHub/JWT/Bearer/AWS/base64 redaction. |
| Sandbox plan + preview hash | `sandbox/adapter.py`, `seatbelt.py`, `bubblewrap.py`, `docker.py` | Plans are real, deterministic, hash-verifiable. |

### Demo / scaffold / preview only
| Area | Evidence | Why incomplete |
|---|---|---|
| Agent loop autonomy | `agent/loop.py` + `llm/mock.py` | `MockLLMClient.choose_tool` returns hard-coded calculator intents; even with `openai` provider, prompt/tool-call contract for LLMs not exercised at scale. No multi-tool reasoning. |
| Subagents | `subagents/runner.py`, `subagents/executor.py` | "Read-only context/result collector" per v2.3.5 honesty note. No independent LLM investigation. |
| MCP | `mcp/runner.py`, `mcp/config.py` | Subprocess JSON shim; no live MCP JSON-RPC `tools/list`/`tools/call`. Classification is keyword-based (`mcp/runner.py:63-70`), not from the server. |
| TUI | `cli_tui.py` (14 lines), `tui/dashboard.py` | One-screen Rich panel; not interactive. |
| Eval / replay / report | `eval/runner.py`, `report/dashboard.py` | Fixture format and runner are solid (v2.5.x) but no public fixtures, no CI-run evals, no regression baseline. |
| Demo workflows | `demo/workflows.py`, `examples/` | Only 4 canned workflows; the `failing-test-repair` workflow drives a hard-coded calculator patch from `mock.py`. |
| `sac queue` / `sac memory` / `sac progress` / `sac rules` | `queue/store.py`, `memory/store.py`, etc. | Each is a ~50-line JSON or Markdown CRUD wrapper. Listed as commands but not part of any real flow. |

### Appears to exist but product semantics are incomplete
| Area | Evidence | Why incomplete |
|---|---|---|
| **Policy presets** | `config.py:151-209` | **`apply_policy_preset` is never called from `SafeCodeConfig.load`**. Setting `policy = "strict"` in `.sac/config.toml` does not actually tighten `shell.allow_readonly_without_confirm`, `shell.allowed_commands`, `sandbox.network_*`, or `hooks.allow_medium_after_apply`. Only `_stricter_policy` name comparison runs. Presets are reachable only via the audit CLI for inspection. See **Finding A** in §3. |
| Sandbox "Noop" execution | `sandbox/execution.py:881-883` | Re-uses `ShellRunner.run(cmd_text, approved=True)` after proposal/approval/claim, so the "Noop sandbox" is policy + approval gating, not containment. CLI calls it "executing." This is honest if you read v2.3.5 docs but misleading in the `sandbox` namespace. |
| Real-LLM agent contract | `llm/openai_client.py`, `agent/schemas.py` | Schemas are real, but the loop is mostly tested against `mock.py`. No retry, no token-budget surfacing in user output, no structured-error recovery. |
| `sac doctor` | `doctor.py:30-80` | Now runs full release preflight on every call. For a non-release-day user (anyone HEAD-ahead of a tag, anyone without `pyproject.toml` matching `__version__`), every doctor row from `release_*` reports red. Doctor is no longer a "is my install OK" command. |
| Setup wizard | `cli.py:32-83`, `setup.py:25-81` | Defaults `--policy normal` (legacy alias) while docs/code push canonical `balanced`; setup writes config but does not apply preset knobs. |
| IDE bridge | `ide/bridge.py`, `cli_ops.py:122-148` | Prints `file://` URIs only. No actual editor integration. |
| Local API facade | `api.py` | Re-export wrapper. No documented usage. |

### Release blocker / productization blocker
| Area | Severity |
|---|---|
| Policy presets advertised but not applied at config load | P1 (see §3 Finding A) |
| `sac doctor` always runs release preflight → red rows in normal use | P1 (see §3 Finding D) |
| Hard-coded version strings drift across CLI panels, signoff text, CI workflow, multiple tests | P2 (see §3 Finding E, §7) |
| `.claude/versions.json` baseline says v2.5.4 while real tag is v2.6.21 | P2 (see §3 Finding F, §8) |
| SKILL.md "Source Of Truth → Git baseline: tag v2.3.5" line directly contradicts the top of the same file | P2 |

---

## 3. Safety Boundaries And Vulnerability Review

### Finding A: Policy presets are decorative — `apply_policy_preset` never runs at config load
Severity: P1
Area: policy / config / safety boundary
Evidence:
- `src/safecode/config.py:62-84` (`SafeCodeConfig.load`) — never calls `apply_policy_preset`.
- `src/safecode/config.py:190-209` (`apply_policy_preset`) — only callers: `policy/audit.py:12` (audit-only) and `tests/test_policy_presets.py`. No runtime path.
- `tests/test_policy_presets.py:91-106` — tests verify the *preset dict* structure but never assert that loading a `.sac/config.toml` with `policy = "strict"` produces a `SafeCodeConfig` with `shell.allowed_commands = ["git","ls","pwd"]`.
- Effect: setting `policy = "strict"` in user config keeps `shell.allowed_commands = ["pwd","ls","echo","git"]` (the default), keeps `hooks.allow_medium_after_apply = False` (already default), keeps `sandbox.network_enabled = False` (already default). For users today the visible effect of switching to `strict` is **zero** beyond policy-name comparison in `_stricter_policy`.

Impact: This is a misleading product behavior: README claims "Choosing a preset" with three CLI/env/config paths, but only `_stricter_policy`'s order-comparison is real. The "strict policy" sold to users does not actually narrow the shell allowlist.

Recommendation: Call `apply_policy_preset(merged)` inside `SafeCodeConfig.load` after env-policy handling, then re-apply `_stricter_policy`-derived `merged.policy`. Add a regression test that loads a TOML with `policy="strict"` and asserts `len(allowed_commands) == 3` and `"echo" not in allowed_commands`.

Tests needed: `tests/test_policy_presets.py` — add `test_load_strict_actually_narrows_allowed_commands`, `test_load_experimental_widens_allowed_commands`, `test_env_strict_overrides_balanced_at_load`.

Release blocker: yes for v2.7 — fix before next product claim.

### Finding B: "Sandbox Noop" execution = approved ShellRunner; product surface still calls it `sandbox`
Severity: P2
Area: sandbox / product framing
Evidence:
- `src/safecode/sandbox/execution.py:881-893` — Noop path calls `ShellRunner(self.project_root, self.config).run(cmd_text, approved=True)`. No FS containment, no network containment beyond the configured `NetworkPolicy`.
- `src/safecode/cli_sandbox.py:30-43` — panel headlined "v2.4.2 Linux Bubblewrap Sandbox Preview" and `Noop backend: [green]executing[/green]` invites the read "sandboxed."
- v2.3.5 docs caveat exists but is not surfaced in `sac sandbox execute` output.

Impact: Confuses users who expect that running through `sac sandbox execute` adds OS-level containment over `sac run`. It does not — the only added value over `sac run --yes` is proposal lifecycle, approval claim, audit and result record. That value is real but mis-named.

Recommendation: Rename the Noop backend label in CLI output to "policy-gated" or "no OS containment (policy + approval only)." Reserve the word `sandbox` in CLI output for backends that actually call `sandbox-exec` / `bwrap` / `docker run`. Move the panel text out of source code (see Finding E).

Tests needed: `tests/test_cli_output_honesty.py` — assert that `sac sandbox plan ... --backend noop` output contains the words "no OS containment".

Release blocker: no.

### Finding C: Hook approvals invalidate on every patch release via `policy_version`
Severity: P2
Area: hooks / UX
Evidence:
- `src/safecode/hooks/approvals.py:31` — `APPROVAL_POLICY_VERSION = f"{SAFECODE_VERSION}-hook-approval-v1"`.
- `src/safecode/hooks/approvals.py:91-103` — `is_approved` requires `approval.policy_version == self._policy_version()`.

Impact: Every `sac release bump 2.6.X` invalidates every stored hook approval. There is no migration path, no warning at load time. A user who carefully approved `pytest -q` in their hook will silently have it rejected after `pip install -U safecode-agent`.

Recommendation: Bind to a *minor-level* (`2.6-hook-approval-v1`) or to the hook-policy schema only. Bind on `hook-approval-v<N>` not on `__version__`. If a runtime version change really must invalidate approvals, log a `runtime` warning and emit a doctor row.

Tests needed: `tests/test_hook_approval_*.py` — add `test_approval_survives_patch_version_bump`.

Release blocker: no, but it's the kind of UX cliff that erodes trust on every update.

### Finding D: `sac doctor` runs full release preflight; red for any developer not exactly at a tag
Severity: P1
Area: doctor / UX
Evidence:
- `src/safecode/doctor.py:46-79` — every `Doctor.run()` call invokes `check_version_consistency`, `check_tag_consistency` (with `_TAG_AUTO`), `check_docs_finalized`, and `run_release_preflight` (which itself invokes `run_release_check`, `run_smoke_tests`, `collect_release_metadata`, `check_docs_finalized` again).
- `src/safecode/release/check.py:41-61` — `_check_tree_clean` runs `git status --porcelain` every doctor call; any uncommitted change → red `release_tag` / `release_preflight` rows.
- `src/safecode/release/smoke.py:50-65` — smoke spins up a Typer CliRunner inside doctor (`sac doctor` invokes itself indirectly through `sac version`).

Impact: A user who just installed SafeCode in a fresh repo or just made any uncommitted change will see two-thirds of `sac doctor` red, every time. This degrades the v1.0.1/v2.3.3 onboarding promise that doctor confirms install health. It also mixes "is my install OK" with "is this checkout releasable" — two unrelated concerns.

Recommendation: Move release diagnostics into `sac release doctor` (or keep them as a `--release` flag). Default `sac doctor` to env-only checks (python, uv, .sac dir, config presence, approval env). Document and test the split.

Tests needed: `tests/test_doctor_release_diagnostics.py` — replace "all rows expected" assertions with "release rows skipped without flag, env rows always run."

Release blocker: yes for the next product-facing release.

### Finding E: Hard-coded version strings drift across CLI panels, signoff text, CI, and tests
Severity: P2 (P1 cumulative)
Area: code quality / release / tests / docs
Evidence:
- `src/safecode/cli_sandbox.py:33,36,41,240,249` — strings "v2.4.2 Linux Bubblewrap Sandbox Preview", "(v2.4.x)" baked into the Rich panel. We are now at v2.6.21.
- `src/safecode/release/signoff.py:57,60` — `"v2.6 final signoff passed."` / `"v2.6 final signoff failed."` hard-coded. Will require source edit at every `v2.7+` release.
- `.github/workflows/ci.yml:34` — `release changelog --from 2.6.14 --to 2.6.17` is a fixed pair, not a "last N versions" command.
- `tests/test_install_update_polish.py:13,89` — asserts `__version__ == "2.6.21"`.
- `tests/test_release_signoff.py:12-65` — every test fixture hard-codes `"v2.6.21"`. Adding v2.6.22 requires editing this file.
- `src/safecode/release/bump.py` — per its docstring, the bumper *modifies* `tests/test_install_update_polish.py`. Source files mutating test assertions is a code smell; the test should read `safecode.__version__` instead of literal strings.

Impact: Every patch release requires touching 4-6 unrelated files; tests are self-referential proofs of the bump tool rather than product invariants.

Recommendation: Replace assertion `__version__ == "X.Y.Z"` with `re.match(r"\d+\.\d+\.\d+", __version__)`. Compute changelog range from git history (`git tag --sort=-v:refname | head -N`) in `release changelog --recent N`. Move panel text out of source — load from a `_VERSION_BANNERS` dict in `src/safecode/release/banners.py` rendered by the runtime version. Stop touching test files from `release bump`.

Tests needed: Delete brittle string assertions; add a single test that asserts `safecode.__version__` is `vX.Y.Z`-shaped and `pyproject.toml["project"]["version"] == safecode.__version__`.

Release blocker: no, but accumulates technical debt every release.

### Finding F: `.claude/versions.json` is stale by 17 versions
Severity: P2
Area: docs / version governance
Evidence:
- `.claude/versions.json:3` — `"current_implemented_tag": "v2.5.4"`.
- `.claude/versions.json:175-233` — `latest_tags` stops at v2.5.4.
- `git tag --sort=v:refname` confirms 17 newer tags through v2.6.21.
- `.claude/skills/current/SKILL.md:11` says baseline v2.6.21; line 387 in the same file says baseline v2.3.5. Internal inconsistency.

Impact: The "source of truth" the CLAUDE.md and version workflow point at is wrong. Future automation that reads `versions.json` to choose the previous tag will choose v2.5.4 → wrong baseline, wrong diff, wrong skill alias.

Recommendation: Regenerate `versions.json` from `git tag` in `release preflight` or as a doctor check. Wire SKILL.md baseline drift detection into `check_docs_finalized` (it currently only checks "mentions the version," not "claims a single baseline").

Tests needed: `tests/test_release_metadata.py` — add `test_versions_json_matches_git_tags`.

Release blocker: no; documentation hygiene.

### Finding G: Project config supplies hook command list verbatim
Severity: P2
Area: hooks / trust boundary
Evidence:
- `src/safecode/config.py:253` — `merged.hooks.after_apply = list(project_config.hooks.after_apply)`. Project config wins outright.
- Approval gate is `is_approved(hook, command)` exact-match; if a user previously approved `pytest -q` in project A, opening project B and triggering `sac apply` where project B's `.sac/config.toml` also defines `pytest -q` as a hook → matches because the **command hash is project-independent**, although `config_hash` (`hooks/approvals.py:133-145`) prevents cross-config replay if the hook set differs.

Impact: The current binding is *config-hash-scoped*, so two unrelated projects with the same `after_apply` list, same allowed_commands list, same policy, and same user will share an approval. This is intended (deduplication) but undocumented. If a user wants per-project hook approvals they have no way to express that.

Recommendation: Add `project_root` (or hash thereof) to `config_hash` payload; document the binding rules in `docs/security/product-security-review-v2.6.md` (which currently does not enumerate them).

Tests needed: `tests/test_hook_approval_*.py` — `test_approval_does_not_carry_across_projects`.

Release blocker: no.

### Finding H: `sac run` returns exit code 0 for blocked / approval-required commands
Severity: P3
Area: shell / UX / scripting
Evidence:
- `src/safecode/cli_core.py:253` — `raise typer.Exit(code=0 if result.exit_code in (0, 125, 126) else result.exit_code)`. Blocked-by-policy (126) and approval-required (125) both surface as exit 0.

Impact: Scripts that depend on `sac run ... && next-step` will run `next-step` even when the command was blocked.

Recommendation: Return the non-zero `exit_code` directly. Add `tests/test_runtime_extensions.py::test_sac_run_blocked_returns_nonzero`.

Release blocker: no.

### Finding I: `sandbox status` panel text drifts and is unread
Severity: P3
Area: docs / CLI surface
Evidence: `cli_sandbox.py:30-43`. v2.4.2 text inside a v2.6.21 product.

Impact: First impression of the most-visible safety command is "this is v2.4." Suggests no one runs `sac sandbox status` during release. Compounds findings F + E.

Recommendation: Replace the panel header with `f"Execution Scope ({__version__})"` and let `SandboxPlanner` provide per-backend mode text.

Release blocker: no.

### Finding J: Hook `_audit` writes two "hook_approval_required" events for a single skipped hook
Severity: P3
Area: audit / cosmetics
Evidence: `src/safecode/hooks/runner.py:38-53` — first emits `hook_approval_required` from `allow_medium_after_apply=False` branch, then runner returns `executed=False, exit_code=125` and the second branch emits a second `hook_approval_required`.

Impact: Audit volume noise; downstream consumers double-count.

Recommendation: Drop the second emission; or change the first to `hook_skipped_by_policy` and keep the runner one as `hook_approval_required`.

Release blocker: no.

### Finding K: `agent/loop.py:488` catches all exceptions in subagent-finding enrichment
Severity: P3
Area: agent loop / observability
Evidence: `try ... except Exception: pass` (loop.py:488-489). Intentional ("fail closed"), but no runtime-log line is emitted.

Impact: Silent context corruption is invisible. Hard to debug.

Recommendation: Log to `runtime.jsonl` at debug level. Same pattern in other "fail closed" sites (recommend an audit).

Release blocker: no.

### Findings not confirmed but worth investigating
- LLM real-mode prompt-injection contract from MCP/subagent observations into `choose_tool` context (`loop.py:471-490` merges arbitrary string content into prompt context with no redaction beyond `redact_secrets`). MCP tool output is already redacted in `mcp/runner.py:190-193`; subagent content merged via `merge_journal_subagent_findings` is **not** secret-redacted at merge time (`subagents/journal_adapter.py`). Not confirmed from current repository evidence whether the journal-adapter pulls already-redacted text or raw text — worth a focused test.
- v1.5.9 metadata-preimage check vs unicode-normalization differences not exhaustively tested.

---

## 4. Functional Design Review

### CLI command inventory (root + groups)
Root commands (via `cli_core` + `cli_ops`): `ask`, `edit`, `apply`, `rollback`, `history`, `run`, `setup`, `rules`, `memory`, `report`, `eval`, `doctor`, `version`.
Groups: `config`, `skills`, `tools`, `index`, `progress`, `context`, `mcp`, `subagent`, `queue`, `export`, `ide`, `release`, `logs`, `audit`, `hooks`, `sandbox`, `agent`, `test`, `demo`, `tui`.
Total visible surface: ~80 commands. First-time user has to read README + tutorials + mvp-user-guide to find a 5-command happy path.

### Concrete command-level recommendations

| Command | Recommendation | Why |
|---|---|---|
| `sac release checklist` | merge into `sac release preflight --dry-run` | Two near-identical aggregators. |
| `sac release smoke` | keep but mark internal / move to `sac release _smoke` | Used inside CI and preflight; not user-facing. |
| `sac release meta` | keep, rename `sac release metadata` for honesty | "meta" is jargon. |
| `sac release signoff` | **delete or merge into preflight**; the version-named "v2.6 final signoff" output is brittle (Finding E) | Adds nothing preflight doesn't, but adds two new failure modes. |
| `sac release changelog` | keep but drive from git, not CLI flags | Brittle CI flag. |
| `sac release bump` | keep but stop modifying tests | Self-referential. |
| `sac release check` + `sac release preflight` | keep one (`preflight`); make `check` an internal helper | Three aggregation levels for one concern. |
| `sac config policy-audit` | rename `sac config doctor` or merge into `sac doctor --policy` | Yet another doctor variant. |
| `sac doctor` | strip release diagnostics; create `sac release doctor` | Finding D. |
| `sac sandbox status` | refresh panel text from runtime version; mark macOS/Linux/Docker honestly | Finding I. |
| `sac sandbox execute --backend noop` | label "policy-gated" not "executing" | Finding B. |
| `sac mcp ...` | keep, mark group `[experimental]` | Subprocess JSON shim, not MCP. |
| `sac subagent ...` | keep, mark group `[experimental]` and reduce README prominence | Read-only context collector. |
| `sac tui dashboard` | remove from README main path | One static panel. |
| `sac queue / memory / progress / rules` | move to `[advanced]` or remove | Stranded surface from v0.3.x; no part of any product flow. |
| `sac export report` | merge into `sac report --output PATH` | Two commands, same intent. |
| `sac ide manifest / open-diff / open-files` | mark `[preview]`, hide from default help | No IDE actually consumes these. |
| (new) `sac start` or `sac quickstart` | **add** | First-run flow today is: `sac setup` → `sac demo materialize ...` → `cd …` → `sac edit …` → `sac apply` → `sac rollback`. Six steps. A `sac quickstart` walking through that interactively would be valuable. |

### Is the v2.6 release tooling too large?
Yes. Original plan: v2.6.0-v2.6.4 (5 versions). Delivered: v2.6.0-v2.6.21 (22 versions), of which 15 are release-tooling related (bump, check, smoke, meta, preflight, docs_guard, signoff, ux, changelog, checklist, CI workflow, doctor release rows, policy-audit, security-review-doc, version-note validation). Three layers of aggregation (check → preflight → signoff) all checking similar things. This is over-engineered for a single-maintainer project at v2.6 with no public release. **Stop growing this surface.**

### CLI complexity for a new user
High. The visible help-text top-level table will show 20+ groups. The README's "Core Commands" lists 9, but the full top-level Typer is much larger. A first-time user has no signal which to use first.

---

## 5. Architecture Quality Review

### Module boundaries
Mostly clean for the v1.x line. Boundaries that are now blurred:

1. **`doctor` ⇄ `release`**: Doctor now imports from `release/docs_guard`, `release/preflight`, `release/version_guard`. Doctor is no longer environment-only. Either rename `Doctor` → `EnvironmentChecks + ReleaseChecks` or split.
2. **`release` is over-sized for its purpose.** 13 modules (bump, changelog, check, checklist, docs_guard, metadata, preflight, signoff, smoke, ux, version_guard, `__init__`). preflight aggregates check+smoke+meta+docs_guard; signoff aggregates preflight+check. Three layers, ~1300 LOC, all running similar git/disk/version inspections.
3. **`cli_sandbox.py` 744 LOC** vs every other CLI module 80-320 LOC. It mixes status, plan, propose, approve, approvals list, revoke, discard, execute, preflight, executions, execution show, stats, prune. Should be split into `cli_sandbox_status.py`, `cli_sandbox_proposal.py`, `cli_sandbox_executions.py`.
4. **`agent/loop.py` does CLI rendering decisions**: passes `pending_action: dict[str, object]` with stringified booleans (`"true"`/`"false"`) used by CLI rendering. The loop should return typed dataclasses, the CLI should stringify.
5. **`cli.py` re-publishes commands at root via list iteration** (`cli.py:87-90`):
   ```python
   for command in core_app.registered_commands:
       app.registered_commands.append(command)
   ```
   This is fragile and reaches into Typer internals. Should use `app.add_typer(core_app, name="...")` with explicit aliasing.

### Circular dependencies / lazy imports
`sandbox/execution.py` uses `from safecode.sandbox.preflight import ...` lazily inside `execute_pending` to "avoid circular import" (`execution.py:640`). Similar lazy imports for `bubblewrap`, `seatbelt`, `docker` (`execution.py:735, 785, 835`). Tells you `sandbox/__init__.py` has a cycle. Worth cleaning before v1.0 contracts are stamped.

### Hidden global state
`SafeCodeConfig.load(project_root)` is called many times per command (cli_core ShellRunner, AuditLogger, AgentOrchestrator, etc.). Reads disk each time, walks parents, runs env-var resolution. No single config singleton. Performance is fine today but is a coupling smell; a config explicitly passed down the stack would be cleaner.

### Public-contract candidates that need to stabilize before v1.0
- `SafeCodeConfig` shape and merge semantics.
- `ToolSpec` registry (the v2.2.0 registry is the closest thing to a public protocol).
- Patch proposal JSON schema (`.sac/pending_patch.json`).
- Audit event schema and hash chain.
- Sandbox proposal/approval/result lifecycle.
- LLM client `ask/plan/choose_tool/propose_patch` contract.

### Module-by-module judgment
- `src/safecode/cli*.py` — needs root-command re-registration cleanup; cli_sandbox needs split.
- `src/safecode/agent/` — clean, but `loop.py:_execute_*` methods are 6 near-duplicate flows; a small Step dispatcher would cut LOC ~30%.
- `src/safecode/sandbox/` — solid contract; execution.py is 1000 LOC and now hosts 4 backend dispatches inline. Move per-backend branches into `SandboxExecutionGate._execute_backend_specific(proposal)` strategy.
- `src/safecode/mcp/` — solid but classification by keyword in client is wrong long-term; should consult registered server schema.
- `src/safecode/release/` — too many modules for what it does (Finding §4 above).
- `src/safecode/config.py` — solid except for the preset application gap (Finding A).
- `src/safecode/doctor.py` — needs split (Finding D).

---

## 6. Code Quality Review

### Consistency issues
- **Exit codes**: `sac run` collapses 125/126 to 0 (Finding H); other commands return non-zero on policy block; `sac release check/smoke/preflight/signoff/bump/meta` use `exit_code(result.ok)` from `release/ux.py`. Three styles.
- **Output formats**: `release/check.py:152-173` renders a labeled text block; `release/smoke.py:120-134` renders a list; `release/preflight.py:66-96` renders yet a third format; `policy/audit.py:95-119` a fourth. No unified `Diagnostic` / `CheckResult` object.
- **Boolean stringification**: `agent/loop.py:104` stringifies booleans (`str(...).lower()`) into `pending_action` dicts. Reading code has to remember whether `"true"` is a string or a bool.
- **Error handling**: `cli_core.py` catches `Exception` broadly in every command; `cli_ops.py` mostly doesn't catch. `cli_sandbox.py` mixes both.

### Brittleness
- Tests hard-code version strings (Finding E).
- `release/bump.py` mutates a test file (Finding E).
- Panel banners hard-code version numbers in CLI source (Finding E, I).
- `_release_checks` in doctor always reaches `git status --porcelain`; CI runs of `sac doctor` on detached HEAD will report odd states.

### Helpers that exist mainly for tests
- `release/check.py`'s `_TAG_AUTO` / `git_tag` injection sentinel and `runtime_version` override exist only because tests need to bypass real git/version. The public surface for "check release" should not need a test seam — make `run_release_check` accept a `GitView` and `VersionView` interface.
- `release/preflight.py`'s `release_check_runner / smoke_runner / metadata_runner / docs_runner` callable injection points exist for tests. Reasonable, but `tests/test_release_preflight.py` should provide a single fixture rather than four.

### Tests-touching-real-worktree risk
- `release/check.py:43-50` calls `git status --porcelain` with `cwd=project_root`. If a test forgets to point project_root at a tmp dir, it scans the actual repo (where the user is running tests). I did not exhaustively trace each test, but `Doctor.run()` is called in `tests/test_doctor_release_diagnostics.py` and the project_root path needs care.
- The repo contains a real `.sac/` directory (logs, checkpoints from earlier development). Tests that initialize `.sac/` in cwd could pollute the developer's working copy if `project_root` isn't carefully tmp-scoped.

### Recommended consolidations
- Introduce `safecode/core/diagnostic.py` with `Diagnostic(name, status: PASS/FAIL/WARN/SKIP, detail, hints: list[str])`. Migrate doctor, release/check, release/smoke, release/preflight, release/signoff, release/docs_guard, policy/audit to produce/render this. Single renderer in `safecode/core/render.py`.
- Replace 3 levels of release aggregation with 1: `Diagnostic.aggregate(diagnostics) -> AggregatedResult`.
- Pull repeated `_check_tree_clean` / `get_exact_git_tag` / `_check_import_version` into `safecode/core/repo_info.py` that returns a cached `RepoInfo` per command invocation.

---

## 7. Test Quality Review

### Strengths
- 73 test files, with very strong coverage of the *security boundaries that matter most*:
  - `test_security_hardening.py`, `test_security_review_docs.py`, `test_migration_hardening.py`
  - `test_sandbox_*_security_evals.py` (5 files, ~225 cross-module tests)
  - `test_mcp_*` (3 files), `test_subagent_orchestration.py` (read in plan)
  - `test_audit_log.py`, `test_patch_apply.py` / `test_patch_validator.py` / `test_patch_parser.py`
  - `test_policy_audit.py`, `test_policy_presets.py`
- The `test_sandbox_cross_backend_security_evals.py` file (82 tests) is genuinely good adversarial coverage (shell=False, hash-before-binary, network-off-default, no `--privileged`, env-not-leaked, etc.).

### Blind spots
1. **No end-to-end test runs the agent loop with a real OpenAI-compatible mock client and a realistic plan**. The `MockLLMClient.choose_tool` returns specific intents for "calculator" goal strings — pattern-matched. Any goal string not containing the right keywords falls back to default. We have no test that `sac agent run "fix the failing test"` over an arbitrary repo actually behaves.
2. **No test verifies `apply_policy_preset` runs at config load** — because it doesn't (Finding A). The audit-only test in `test_policy_presets.py:91-106` validates preset *structure* but not *application*.
3. **Brittle version-string tests** dominate the release suite (Finding E). 16+ tests reference `"2.6.21"` literally.
4. **No test verifies `cli_sandbox.py` panel text matches runtime version** (Finding I).
5. **No regression test for `sac doctor` row count in a fresh `git init` repo** — Finding D would have been caught.
6. **No integration test that runs `sac doctor` from a tmpdir, expects mostly green** — only unit tests with mocked dependencies.
7. **No CI run of the eval suite** (`sac eval` exists; tests check the runner; no replay-based regression gate).
8. **No adversarial test for prompt-injection through MCP/subagent observations** — the redaction surface boundary in `merge_journal_subagent_findings` is unverified.

### Tests that should be refactored or made less brittle
- `tests/test_release_signoff.py` — drop hard-coded `"v2.6.21"`; use a fixture-version param.
- `tests/test_install_update_polish.py:13,89` — replace literal with `re.fullmatch(r"\d+\.\d+\.\d+", __version__)`.
- `tests/test_release_metadata.py` — generate expected note list from git tags, not literal.
- All `tests/test_release_*.py` — share `release_state(version)` builder fixture; today each test rebuilds the whole `ReleaseCheckResult/PreflightResult` literal tree.
- `tests/test_doctor_release_diagnostics.py` — assert *which kinds of checks run by default*, not that release rows are always present.

### P0/P1 tests to add (release-before-tag suite)
- P1 `test_apply_policy_preset_runs_at_config_load` — Finding A.
- P1 `test_doctor_without_release_flag_skips_release_rows` — Finding D.
- P1 `test_versions_json_consistent_with_git_tags` — Finding F.
- P1 `test_skill_md_baseline_consistent_with_version_implementation_matrix` — Finding F.
- P1 `test_cli_sandbox_panel_uses_runtime_version` — Finding I.
- P1 `test_sac_run_returns_nonzero_when_blocked` — Finding H.
- P1 `test_hook_approval_survives_patch_version_bump` — Finding C.
- P1 `test_subagent_findings_redacted_at_merge` — covers prompt-injection through journal.
- P2 `test_mcp_runner_subprocess_shell_false_under_all_calls` — strengthens the v2.4.3 cross-backend invariant for MCP.
- P2 `test_changelog_command_derives_range_from_git` — Finding E (CI brittleness).

### Recommended release-before-tag suite
```
PYTHONPATH=src python3 -m pytest -q                          # full regression
PYTHONPATH=src python3 -m pytest -q -k security              # security focus
PYTHONPATH=src python3 -m safecode.cli release smoke         # already in CI
PYTHONPATH=src python3 -m safecode.cli release meta          # already in CI
PYTHONPATH=src python3 -m safecode.cli release preflight     # local only
```

---

## 8. Documentation And Version Governance Review

### Drift findings
| Source | Claim | Actual | Severity |
|---|---|---|---|
| `.claude/versions.json` | `current_implemented_tag = v2.5.4`, latest_tags ends at v2.5.4 | tag is v2.6.21, 17 newer tags exist | P2 |
| `.claude/skills/current/SKILL.md:11` | "Git baseline: tag v2.6.21" | true | OK |
| `.claude/skills/current/SKILL.md:387` | "Git baseline: tag v2.3.5" | contradicts line 11 | P2 |
| `docs/productization-roadmap-to-claude-code.md` | v2.6 plans v2.6.0–v2.6.4 (5 subtasks) | delivered v2.6.0–v2.6.21 (22 subtasks), 17 of them ad-hoc | P2 |
| `docs/release_roadmap_v0_1_to_v1_0.md` (filename) | "v0.1 to v1.0" | covers v0.1.x to v1.7.x | P3 |
| `docs/security/product-security-review-v2.6.md` | checklist `[x] Policy names and aliases are explicit` `[x] Safety invariants are documented and audited` | True for *names*; **but `apply_policy_preset` is not wired** (Finding A). Doc overstates enforcement. | P1 |
| `docs/version_implementation_matrix.md:226` (v1.9.5) | `sac agent resume/abort/explain-last-failure` available | Need confirmation — not verified from current evidence; the loop has no `resume()` method visible | not confirmed |
| `README.md:166-194` Release Flow | `git tag -a v2.6.13 -m "..."` | Workflow expects exact tag; signoff also expects exact tag. README's example is fine, but does not warn the user that uncommitted changes break tag consistency check | P3 |

### Was the v2.6.x expansion reasonable?
**Partially.** v2.6.0 (policy presets), v2.6.1 (migration hardening), v2.6.6 (tag consistency), v2.6.19 (policy audit), v2.6.20 (security review doc) — all defensible product-hardening work. v2.6.7 (next-step polish), v2.6.12 (note-heading validation), v2.6.13 (workflow docs), v2.6.14 (release UX polish), v2.6.16 (checklist upgrade), v2.6.21 (final signoff aggregating things that were already aggregated) — these are *meta-tooling polish on tools that have no users yet*. The cost is real: 13 new release modules, 12 new tests, complex three-layer aggregation, brittle version-string tests, and a doctor command that now fails for normal users.

**Should v2.6.x be formally closed?** Yes. The signal-to-noise on additional v2.6.x patches is now poor. Move to v2.7.x with a *halt-feature-growth* theme.

---

## 9. Next-Stage Roadmap Recommendation

### Strategic call
- v2.6.x should be **declared complete** as of v2.6.21.
- v2.7.x theme: **"Consolidation: Honesty, Onboarding, and Wiring."** No new sandbox backends. No new MCP capabilities. No new release tooling. The next phase fixes things that are *claimed but not wired* (presets), *grown but misshapen* (release surface, doctor), and *visible but inaccurate* (version banners).
- The next thing to grow is **the agent loop's real-LLM evidence** and **a stable public contract for the safety substrate** — but only after the consolidation pass.

### A. Immediate Fix Versions: v2.7.0 – v2.7.3

#### v2.7.0 — `policy-preset-wiring`
- Theme: make `policy = "strict"` actually do what users think it does.
- Why: Finding A. Highest-impact mismatch between docs and code.
- Affected modules: `src/safecode/config.py`, `src/safecode/setup.py`, `tests/test_policy_presets.py`, `docs/security/product-security-review-v2.6.md`.
- Tasks:
  1. Call `apply_policy_preset(merged)` inside `SafeCodeConfig.load` after env-policy resolution; document the order: user-toml → project-toml stricter-merge → env-policy stricter-merge → preset application.
  2. Make `setup.write_setup` default `policy="balanced"` (canonical name).
  3. Add a `SafeCodeConfig.policy` Pydantic validator that warns when an unknown name is loaded.
- Acceptance: loading a `.sac/config.toml` with `policy = "strict"` returns `shell.allowed_commands == ["git", "ls", "pwd"]` and `hooks.allow_medium_after_apply == False`; loading `"experimental"` returns the experimental allowlist.
- Tests added/modified: `test_load_strict_actually_narrows_allowed_commands`, `test_load_experimental_widens_allowed_commands`, `test_env_strict_overrides_balanced_at_load`, fix `test_setup_wizard.py` default expectation.
- Release blocker: yes.

#### v2.7.1 — `doctor-release-split`
- Theme: bring back environment-only `sac doctor`.
- Why: Finding D.
- Affected modules: `src/safecode/doctor.py`, `src/safecode/cli_ops.py`, `tests/test_doctor_release_diagnostics.py`, `tests/test_install_update_polish.py`.
- Tasks:
  1. `Doctor.run()` returns only env checks by default.
  2. Add `Doctor.run_release()` and `sac doctor --release` flag (or `sac release doctor`).
  3. Update tests; document the split in README.
- Acceptance: `sac doctor` in a fresh `git init`'d repo prints 8 green rows; `sac doctor --release` reproduces previous output.
- Release blocker: yes.

#### v2.7.2 — `version-string-decoupling`
- Theme: stop hard-coding version strings in source and tests.
- Why: Finding E, I.
- Affected modules: `src/safecode/cli_sandbox.py`, `src/safecode/release/signoff.py`, `src/safecode/release/bump.py`, `tests/test_install_update_polish.py`, `tests/test_release_signoff.py`, `.github/workflows/ci.yml`.
- Tasks:
  1. Build `safecode/release/banners.py` with version-derived panel text.
  2. Replace literal `"2.6.21"` in tests with `re.fullmatch(r"\d+\.\d+\.\d+", __version__)` patterns.
  3. Stop `release bump` from modifying tests.
  4. CI changelog uses `--recent 5` (compute from git) instead of fixed `--from/--to`.
- Acceptance: `release bump 2.7.0` modifies only `pyproject.toml` and `src/safecode/__init__.py`; `sac sandbox status` prints "Execution Scope (2.7.0)"; `pytest -q` passes without any other source edits.
- Release blocker: yes.

#### v2.7.3 — `hook-approval-policy-version-stability`
- Theme: stop invalidating hook approvals every patch release.
- Why: Finding C.
- Affected modules: `src/safecode/hooks/approvals.py`, `tests/test_hook_approval_*.py`, docs.
- Tasks:
  1. Change `APPROVAL_POLICY_VERSION` to `"hook-approval-v1"` (no runtime version).
  2. Document approval invalidation conditions in security review doc.
  3. Add migration test: approvals stored under v2.6.21 still match after `__version__` change.
- Acceptance: hook approved at v2.6.21 still matches at v2.7.x.
- Release blocker: no.

### B. Productization Versions: v2.7.4 – v2.7.8

#### v2.7.4 — `release-surface-collapse`
- User problem: `sac release` has 8 subcommands doing 4 distinct things.
- Product change: keep `preflight`, `bump`, `changelog`. Delete `signoff` (or fold into preflight). Make `checklist` an alias for `preflight --dry-run`. Mark `check`, `smoke`, `meta` as internal helpers.
- Technical change: introduce `safecode/core/diagnostic.py` `Diagnostic` dataclass; collapse three aggregation layers into one.
- Acceptance: `sac release --help` shows 3 user-facing subcommands; preflight passes; CI green.
- Risks: someone scripts against `sac release check` exit code; mitigate via deprecation note in `--help`.

#### v2.7.5 — `cli-surface-trim-and-quickstart`
- User problem: first-time user lost in 20+ command groups.
- Product change: README's "Core Commands" section shrunk to a 5-step quickstart. Add `sac quickstart` that walks setup → demo materialize → edit → apply → rollback in one interactive flow. Hide `queue`, `memory`, `progress`, `rules`, `tui`, `ide`, `export` under `--advanced` or remove from default help.
- Technical change: introduce Typer command groups with `hidden=True`; add `cli_quickstart.py`.
- Acceptance: `sac --help` shows ≤ 10 top-level groups; `sac quickstart` succeeds on a fresh `git init`.
- Risks: hiding commands annoys existing power users; mitigate via `sac --advanced --help`.

#### v2.7.6 — `honest-sandbox-and-mcp-surface-v2`
- User problem: `sac sandbox status` text frozen at v2.4.2; `sac sandbox execute --backend noop` says "executing."
- Product change: rename Noop label to "policy-gated (no OS containment)"; update panel headers to runtime-version-derived banners. Mark MCP/subagent groups `[experimental]` in help; reduce README prominence.
- Technical change: see v2.7.2.
- Acceptance: `sac sandbox status` mentions OS containment status; `sac --help` shows `[experimental]` on MCP/subagent.
- Risks: none significant.

#### v2.7.7 — `agent-loop-realmode-evidence`
- User problem: agent loop is almost entirely mock-driven; no evidence it works on real tasks.
- Product change: add 3 realistic eval fixtures (FastAPI bug fix, CLI feature, docs edit) that the loop must complete against an OpenAI-compatible mock that *isn't* keyword-matching; add a "fail closed if LLM contract violated" telemetry row.
- Technical change: extend `eval/runner.py` with `--mode loop` to drive the full `AgentLoop` instead of replay; reuse existing v2.5.x fixtures.
- Acceptance: `sac eval --mode loop` runs three fixtures locally with a stub LLM.
- Risks: stub LLM may diverge from real model behavior — document as preview.

#### v2.7.8 — `docs-and-versioning-housekeeping`
- User problem: version index, SKILL baseline, roadmap doc are inconsistent; stale `versions.json`.
- Product change: regenerate `versions.json` from `git tag --sort=v:refname`; collapse the duplicate "Source Of Truth" section in SKILL.md; rename `release_roadmap_v0_1_to_v1_0.md` to `release_roadmap_v0_1_to_v2_x.md` or split. Update `productization-roadmap-to-claude-code.md` to reflect actual v2.6 work and v2.7 plan.
- Technical change: add `sac release sync-versions-json` (or fold into preflight).
- Acceptance: `versions.json.current_implemented_tag == git describe --tags`.
- Risks: none significant.

### C. Long-term Architecture: v2.8.x or v3.0 (plan only)

| Area | Phase | Why wait |
|---|---|---|
| Unified `Diagnostic` / `CheckResult` substrate across doctor/release/policy/audit | v2.8.0 | Touches too many files for one patch; needs v2.7.4 surface trim first. |
| Sandbox backend strategy split (one module per backend, `execute_pending` ≤ 100 LOC) | v2.8.1 | Cleanup, not user-visible. |
| Real MCP JSON-RPC client (full `tools/list`, `tools/call`, capability negotiation) | v2.8.x | Major engineering; needs schema-driven classification. |
| Real subagent dispatch with bounded LLM calls and merge-review | v2.8.x | Needs real LLM contract evidence (v2.7.7). |
| TUI rewrite with prompt-toolkit | v3.0 | Current TUI is one panel; full TUI is large scope. |
| Public Python API (`SafeCodeLocalAPI` documented) with semver guarantees | v3.0 | Requires public contract freeze on config, audit schema, tool registry. |
| Signed audit anchors (key material in keychain) | v3.0 | Cross-platform key storage is significant work. |

### Directions that should *not* be pursued now
1. **More release tooling.** Stop. The release surface is already over-engineered for a single-tag-per-week cadence.
2. **A fifth sandbox backend** (gVisor, Firecracker, podman). Three preview backends with cross-backend evals is plenty until v2.7.7 proves the loop uses them.
3. **A real Claude-Code-parity TUI / editor plugin.** Premature — the agent's actual reasoning is not yet good enough to justify the integration cost.
4. **A team-trust / cloud-sync feature.** v1.1.x suggested this; the project does not have the user base to justify it. Stay local.

### Modules that need stable public contracts first
- `SafeCodeConfig` (with preset application baked in).
- `ToolSpec` registry.
- Pending-patch JSON schema (`.sac/pending_patch.json`).
- Audit `AuditEvent` schema and hash chain.
- `SandboxExecutionProposal/Result/Approval` lifecycle.

### Areas that need feature freeze until stabilized
- Release tooling (freeze: 2-3 release surface trim only).
- Doctor command (freeze: split-and-shrink only).
- MCP surface (freeze: subprocess shim until real JSON-RPC arrives).
- Sandbox backends (freeze: no new backends; only the wiring/honesty fixes).

### Productization checklist required before v1.0
- [ ] Policy presets actually applied at config load.
- [ ] `sac doctor` is env-only by default.
- [ ] No hard-coded version strings outside `__init__.py` and `pyproject.toml`.
- [ ] Hook approvals survive patch version bumps.
- [ ] `sac sandbox status` and `cli_sandbox.py` banners are version-derived.
- [ ] `sac --help` shows ≤ 10 user-facing top-level entries.
- [ ] A documented `sac quickstart` flow.
- [ ] At least one real-LLM eval fixture in CI.
- [ ] `versions.json` consistent with git tags (enforced by preflight).
- [ ] SKILL.md baseline consistent with implementation matrix (enforced).
- [ ] Single `Diagnostic` substrate across doctor / release / policy-audit.

### Top 5 issues to prioritize now
1. **Finding A — policy presets not wired** (P1).
2. **Finding D — `sac doctor` red-by-default** (P1).
3. **Finding E — hard-coded version strings** (P1 cumulative).
4. **Finding C — hook approvals invalidate on each release** (P2 but high-friction).
5. **Finding F — `versions.json` / SKILL.md baseline drift** (P2 governance).

---

## 10. Final Conclusion

- **Maturity rating:** **advanced prototype**, leaning toward **pre-product** for the safety substrate. The agent itself is still demo-grade. The release tooling is over-engineered for the maturity of the agent it claims to release.
- **Biggest risk:** product positioning drift. The repository says "Claude Code-like local runtime" but the last 17 versions have been *release-tooling polish*. The thing that would actually move the product forward (real agent loop on real tasks) has not received attention since v2.3.6.
- **Biggest strength:** the safety substrate is unusually disciplined for an individual project — hash-chained audit, atomic approvals, claim-based single-use sandbox approvals, deep command-policy hardening, layered preset-derived config, and broad adversarial test coverage. This is the genuinely portfolio-worthy core.
- **Suitability:**
  - As a **resume project**: yes, strong. Emphasize the safety substrate and v1.5.x security-hardening branches. Do not lead with the release tooling.
  - As an **RA / research direction**: yes — agent-safety boundaries are a publishable research surface; SafeCode is concrete enough to study (e.g., approval-claim atomicity, redaction edge cases).
  - As an **agent-security project**: yes — that *is* the project; double down on prompt-injection through MCP/subagent observations, on policy enforcement, and on regression evals.
  - As an **open-source product**: not yet. The first-run UX is fragmented, the policy-preset claim is unwired, and the release surface signals "release process" louder than the product itself.
- **One-sentence judgment:** **Do not add new features now — pause v2.6 expansion, declare v2.7.x a consolidation line (preset wiring, doctor split, version-string decoupling, hook-approval stability, CLI surface trim), then re-evaluate whether the agent loop deserves real-LLM investment.**

---

## 11. Summary Tables

### Top 10 findings

| # | Finding | Severity | Area | Release blocker? |
|---|---|---|---|---|
| 1 | A — policy presets never applied at config load | P1 | policy / config | yes |
| 2 | D — `sac doctor` always runs release preflight | P1 | doctor / UX | yes |
| 3 | E — hard-coded version strings in source, tests, CI | P1 cumulative | code quality / tests / release | no, but blocks next release |
| 4 | C — hook approvals invalidated by every patch bump | P2 | hooks / UX | no |
| 5 | F — `.claude/versions.json` baseline stale by 17 tags; SKILL.md self-contradicts | P2 | docs / governance | no |
| 6 | B — Noop sandbox execute = approved ShellRunner, mis-labelled | P2 | sandbox / product framing | no |
| 7 | G — Project config dictates `after_apply` list verbatim; approval binding undocumented | P2 | hooks / trust boundary | no |
| 8 | I — `sac sandbox status` panel frozen at v2.4.2 in a v2.6.21 product | P3 | docs / surface | no |
| 9 | H — `sac run` returns exit 0 for blocked commands | P3 | shell / UX | no |
| 10 | J — Duplicate `hook_approval_required` audit events per skipped hook | P3 | audit | no |

### Release blockers (must fix before next user-facing release)
1. Finding A — wire `apply_policy_preset` at config load.
2. Finding D — split env-doctor from release-doctor.
3. Finding E — remove hard-coded version strings (cumulative debt).

### Recommended next 3 versions
- **v2.7.0** — policy-preset wiring (Finding A).
- **v2.7.1** — doctor / release split (Finding D).
- **v2.7.2** — version-string decoupling (Finding E, I).

### Not recommended right now (3 categories)
1. **Any new sandbox backend (gVisor, Firecracker, podman, etc.).**
2. **Any new `sac release …` subcommand or aggregation layer.**
3. **Real MCP JSON-RPC client, real concurrent subagents, full TUI/IDE plugin** — defer to v2.8.x / v3.0 after consolidation.

### Draft prompt for Claude Code / Codex to implement the first batch of fixes

```
You are implementing SafeCode Agent v2.7.0 — "policy-preset-wiring".

Scope (single small PR):
1. In src/safecode/config.py, inside SafeCodeConfig.load, after the existing
   env-policy resolution block, call apply_policy_preset(config) before
   returning. Do this once and only once, regardless of how config.policy
   was set.
2. In src/safecode/setup.py, change the default value of `policy` from "normal"
   to "balanced". Update the CLI option default in src/safecode/cli.py.
3. In tests/test_policy_presets.py, add three new tests that load a real
   `.sac/config.toml` from a tmp dir and assert that:
   - policy="strict"      → shell.allowed_commands == ["git", "ls", "pwd"]
   - policy="experimental" → "cat" in shell.allowed_commands and
                              hooks.allow_medium_after_apply is True
   - SAFECODE_POLICY="strict" overrides a user policy of "balanced"
4. In tests/test_security_hardening.py, verify the
   "project config cannot lower user policy" invariant still holds after
   preset application.
5. Update docs/security/product-security-review-v2.6.md to add a line under
   "Configuration Policy": "Selecting a policy applies preset values for
   shell.allowed_commands, sandbox network defaults, and
   hooks.allow_medium_after_apply at config load."

Hard constraints:
- Do not change the merge order: trusted user → stricter merge with project →
  env stricter merge → preset application.
- Do not remove or rename POLICY_PRESETS, normalize_policy_name,
  apply_policy_preset, or KNOWN_POLICY_NAMES.
- All existing tests must continue to pass (run
  `PYTHONPATH=src python3 -m pytest -q`).
- Preserve "project-local config cannot lower user-level safety"
  — verify with both the existing test in test_security_hardening.py
  and a new test that mixes user-policy=strict with project-policy=experimental
  and asserts the merged policy stays strict and its preset still applies.
- Do not bump the version, tag, or touch the release tooling. v2.7.0
  bumping is a follow-up PR.

Deliverables:
- src/safecode/config.py     (apply_policy_preset call in load)
- src/safecode/setup.py      (default "balanced")
- src/safecode/cli.py        (CLI option default "balanced")
- tests/test_policy_presets.py (3 new tests, load-time semantics)
- tests/test_security_hardening.py (1 new test: preset + lowered-policy
  protection)
- docs/security/product-security-review-v2.6.md (one-line clarification)

When you have a clean PR, post the diff. No release commands needed.
```

End of report.
