---
name: Version 1.2.3 Complete
description: >
  v1.2.3 captures v1.2.3. Reference this skill when inspecting or extending this historical SafeCode Agent version.
---

# Version 1.2.3 - v1.2.3 snapshot

## Status
Implemented and tagged as `v1.2.3` at `3bc5d8e`.

## Base Version
- Depends on: `v1.2.2`
- Stage: `v1.2.x: Production Hardening`
- Version index: `docs/version_implementation_matrix.md`

## Implemented Capability
`v1.2.3` implements the `v1.2.3` milestone from `v1.2.x: Production Hardening`.

- Historical branch: `v1.2.3-real-llm-provider`
- Main entry: `src/safecode/llm/factory.py`、`src/safecode/llm/openai_client.py`

## Main Files
- `src/safecode/llm/factory.py`
- `src/safecode/llm/openai_client.py`

## Acceptance Commands
- 默认 mock 测试通过，真实 LLM 需 API key

## Backward Compatibility Requirements
- Preserve the safety-first patch flow: preview diff, checkpoint before writes, audit after actions, rollback available.
- Do not weaken command, filesystem, network, approval, audit, or sandbox boundaries introduced by this or earlier tags.
- Prefer additive changes when building from this tag; document any deliberate behavior change in version notes.

## Notes For Future Work
- Treat this file as historical implementation context, not a request to modify the tag commit.
- Build new work on `main` or a fresh work branch, then create a new tag after verification.
- If checking out this tag, expect a detached HEAD; create a branch before editing.
