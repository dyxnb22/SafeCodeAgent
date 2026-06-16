# Contributing to SafeCode Agent

Thank you for your interest in contributing.

## Development setup

```bash
git clone <repo>
uv sync
uv run sac doctor
PYTHONPATH=src python3 -m pytest -q
```

## Running tests

```bash
# Targeted (for a narrow change):
PYTHONPATH=src python3 -m pytest tests/test_<module>.py -q

# Full regression (required before cross-cutting changes):
PYTHONPATH=src python3 -m pytest -q
```

CI installs via `pip install -e ".[dev]"` and runs `python -m pytest -q`.

## Code standards

- Type hints for new or changed public functions and Pydantic models.
- No auto-apply, auto-commit, or auto-push without explicit user action.
- Preserve existing command names and safety gates unless a version plan
  explicitly declares a breaking change.
- Use structured parsing and typed models; avoid ad hoc string state.
- Add or update tests for every security, sandbox, policy, patch, audit,
  approval, or rollback change.

## Adding a new native tool

1. Define a `NativeToolSpec` in `src/safecode/tools/registry.py`.
2. Implement the handler in the appropriate `cli_*.py` or domain module.
3. Register it in `NativeToolDispatcher._build_dispatcher()`.
4. Add audit event type if the tool writes or executes.
5. Add tests in `tests/test_native_tools_*.py`.
6. Document in `docs/version-notes/vX.Y.Z-your-tool.md`.

See `docs/version-notes/v4.21.0-write-side-native-tools.md` for the pattern.

## Adding a new LLM provider

1. Implement the `LLMClient` protocol in `src/safecode/llm/<provider>_client.py`.
2. Add the provider key to `src/safecode/llm/factory.py`.
3. Add live smoke tests in `tests/live/test_live_providers.py`.
4. Document in `docs/providers.md`.

## Test conventions

- **Targeted tests:** run only the module-level tests for your change first.
- **Full regression:** required for changes to agent loop, context, policy,
  sandbox, MCP, audit, checkpoint, or CLI surface.
- **Snapshot tests:** use for contract stability (JSON envelopes, audit
  schemas, tool registry). Update snapshots intentionally, never silently.
- **Mock by default:** `SAFECODE_LIVE_TESTS=1` gates all real provider calls.
  Tests must pass without a key.

## Updating the golden demo

When you change user-facing behavior (new command, changed output format,
new safety gate message), update:
- `examples/golden-demo/demo/expected-transcript.md`
- `docs/demo/portfolio-demo.md`

Run `examples/golden-demo/demo/run-demo.sh` to verify the demo still works.

## Commit message style

```
type(scope): short description

Body explaining why, not what. Link to version plan if applicable.
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.
