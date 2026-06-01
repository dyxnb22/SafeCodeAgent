# SafeCode Product Security Review v2.6

## Scope

This review covers the v2.6 product-hardening surface: configuration policy,
sandbox defaults, hook execution, release gates, and trust boundaries between
user-level intent and project-controlled files.

## Configuration Policy

- Canonical policies are `strict`, `balanced`, and `experimental`.
- Legacy aliases `normal` and `learning` remain accepted for compatibility.
- Unknown `SAFECODE_POLICY` values warn and are ignored.
- Unknown project config policy names cannot override a known user policy.
- Effective policy presets are applied during config load after user, project,
  and env-policy strictness are merged.
- `sac config policy-audit` checks known policy names, aliases, project/env
  policy values, and preset invariants.

## Sandbox Defaults

- `sandbox.restrict_to_project_root` stays enabled across policy presets.
- `sandbox.network_enabled` defaults to disabled across policy presets.
- Sensitive names such as `.env`, credentials, tokens, and key files stay in
  the default deny-oriented discovery surface.
- Docker, macOS Seatbelt, and Linux Bubblewrap are preview/adapter backends;
  unavailable backends must fail honestly rather than imply containment.

## Hooks

- Project hooks are project-controlled and do not auto-approve medium-risk
  commands by default.
- `allow_medium_after_apply` is conservative in `strict` and `balanced`.
- Hook approvals and sandbox approvals are stored outside the project root.
- Hook approvals are bound to a hook-approval schema version, user, command,
  and hook-relevant config rather than to every patch release number.

## Release Gates

- `sac release check` verifies package/runtime version consistency, exact tag
  consistency, and working-tree cleanliness.
- `sac release smoke` checks import/version, CLI version, version consistency,
  policy names, and docs finalization.
- `sac release meta` audits version notes, note headings, duplicate notes, tags,
  and SKILL baseline freshness.
- `sac release preflight` aggregates release check, smoke, metadata, and docs.
- CI runs full regression plus checks that do not require HEAD to be exactly
  tagged.

## Trust Boundaries

- User-level configuration is trusted more than project-local configuration.
- Project-local configuration cannot lower user-level safety.
- Project-local configuration cannot enable network access when user config
  disables it.
- Project-local config can request hooks, but approval policy and audit logs
  remain outside the project root.
- Release tags are not trusted unless they match package metadata and
  `safecode.__version__`.

## Review Checklist

- [x] Policy names and aliases are explicit.
- [x] Unknown policy handling fails closed or warns.
- [x] Safety invariants are documented and audited.
- [x] Release gates cover version, tag, docs, and metadata drift.
- [x] CI avoids exact-tag-only checks.
