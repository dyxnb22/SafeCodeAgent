# SafeCode Agent LLM Providers (v3.2)

This document describes the supported LLM provider contract introduced in v3.2.
The contract covers provider selection, configuration, retry semantics, streaming,
structured-output validation, cost accounting, and fan-out/fallback routing.

For the full list of stable local safety contracts, see
[docs/public-contracts.md](public-contracts.md).

---

## Supported Provider Keys

| Key | Type | Notes |
|---|---|---|
| `mock` | Stable default | Deterministic mock client; no network; used in all local tests |
| `openai` | Supported | OpenAI-compatible chat completions endpoint |
| `openai-compatible` | Supported | Any OpenAI-compatible endpoint (local models, proxies) |
| `anthropic` | Supported | Anthropic Messages API |
| `deepseek` | EXPERIMENTAL | DeepSeek API via OpenAI-compatible path; see DeepSeek section below |

Set via `config.toml` or the `SAFECODE_LLM_PROVIDER` environment variable.
Both override the default `mock` provider.

---

## Config Reference

`LLMConfig` fields in `.sac/config.toml` under `[llm]`:

| Field | Type | Default | Description |
|---|---|---|---|
| `provider` | string | `"mock"` | Primary provider key |
| `model` | string | `"gpt-4.1-mini"` | Model name for the primary provider |
| `base_url` | string | `"https://api.openai.com/v1/chat/completions"` | Endpoint URL |
| `fallback_provider` | string or null | `null` | Optional fallback provider key |
| `fallback_model` | string or null | `null` | Model for the fallback provider |
| `fallback_base_url` | string or null | `null` | Endpoint URL for the fallback provider |

Environment variable overrides: `SAFECODE_LLM_PROVIDER`, `SAFECODE_LLM_MODEL`.

---

## Retry Semantics

All real providers (`openai`, `openai-compatible`, `anthropic`, `deepseek`) wrap requests in
`retry_call()` with bounded retry and jitter:

- **Retryable**: HTTP 408, 429, 502, 503, 504, and `URLError` (connection-level failures).
- **Not retried**: other 4xx/5xx, policy blocks (`PermissionError`), hard contract
  violations (`ValueError`), `RecoverableContractFailure` values.
- **Parameters**: `max_attempts=3`, `base_delay=0.5s`, jitter = `uniform(0.5, 1.5) * base_delay * 2^attempt`.
- **Retry-After**: honored when the `Retry-After` header is present on 429 responses;
  capped at 30 seconds to prevent server-driven denial-of-service.
- **RateLimitError**: when 429 retries are exhausted, a typed `RateLimitError` is raised
  so callers can distinguish rate-limit exhaustion from other transport failures.

## Reliability Knobs (v4.10.3+)

The following `LLMConfig` fields control per-request reliability. All fields are
bounded and configurable via `.sac/config.toml` under `[llm]`:

| Field | Default | Description |
|---|---|---|
| `request_timeout_seconds` | `60` | Per-request HTTP timeout in seconds (minimum 1) |
| `max_retries` | `3` | Maximum retry attempts (minimum 1) |
| `retry_base_delay_seconds` | `0.5` | Base jitter delay in seconds (minimum 0.0) |

**Progress callback** (optional, programmatic API only): `OpenAICompatibleLLMClient`
accepts an optional `progress_callback(stage: str)` at construction. The stage names are:
`request_started`, `retrying`, `rate_limited`, `response_received`, `parsed`, `failed`.
This is not SSE or token streaming — it reports lifecycle stages only.

**Network policy invariant**: all reliability knobs are applied after the network policy
gate. Increasing timeout or retry count never bypasses the policy check.

---

## Structured Output Validation

Provider JSON responses are parsed through `validate_provider_json()` before
they are cast to agent contract models:

- **Soft failures** → `RecoverableContractFailure` (returned, not raised):
  invalid JSON, missing `type` field, missing required fields, Pydantic validation errors.
- **Hard failures** → `ValueError` (raised, fail-closed):
  structurally valid JSON with a wrong contract type.
- The agent loop may retry `choose_tool` once on `RecoverableContractFailure`.
- `parse_agent_contract_response()` is unchanged for non-provider code paths.

---

## Streaming

Providers that implement `SupportsStreaming` expose `stream_chat(messages)`:

- Returns an `Iterator[StreamChunk]`. Each chunk has `delta: str` and
  `finish_reason: str | None`.
- `aggregate_chunks()` collects chunks into a `StreamResult(text, finish_reason)`.
- SSE parsing: `parse_sse_line()` / `parse_sse_stream()` for OpenAI SSE format;
  `_parse_anthropic_sse()` for Anthropic event types.
- Cancellation is fail-closed: partial output is discarded, session state is not
  mutated if the stream is abandoned mid-way.
- `StreamError` is raised on hard stream failures (malformed JSON, connection errors).

---

## Cost Accounting

After each successful API call, token usage is persisted to
`.sac/sessions/<session_id>/cost.json`:

- `TokenUsage` fields: `prompt_tokens`, `completion_tokens`, `total_tokens`, `cost_usd`.
- `cost_usd` is always `null` until pricing is wired.
- `SessionCostAccumulator` accumulates across calls for the same session atomically.
- OpenAI usage: `usage.prompt_tokens`, `usage.completion_tokens`.
- Anthropic usage: `usage.input_tokens` → `prompt_tokens`, `usage.output_tokens` → `completion_tokens`.

---

## Fan-out / Fallback Config

When `fallback_provider` is set, the factory returns a `FanOutLLMClient`:

- **Trigger**: `RuntimeError` from any primary method (transport/network failures).
- **Not triggered by**: `PermissionError` (network policy block), `ValueError`
  (hard contract violation), `RecoverableContractFailure` (returned value).
- **Behavior on trigger**: emits a `RuntimeWarning` with method name and exception
  type (no prompt content), then delegates to the fallback.
- **Fallback failure**: raises the fallback's error (fail-closed; no silent data loss).
- **Network policy**: both primary and fallback must pass `NetworkPolicy.assert_allowed()`
  at init time.
- **No nesting**: the fallback client has its own `fallback_*` fields cleared to
  prevent recursive fan-out.

---

## Live CI Lane

A `live-provider` CI job is available but **advisory and opt-in**:

- Gated by the repository variable `ENABLE_LIVE_LLM_TESTS=true`.
- Set `SAFECODE_LIVE_TESTS=1` locally to run `tests/live/` tests.
- Does not block merges (`continue-on-error: true`).
- No API keys in any repository file; injected via GitHub Actions secrets at runtime.

### Release Train History (v3.10.1)

| Release | Live-provider lane status | Promoted to blocking? | Notes |
|---|---|---|---|
| v3.10.0 | Advisory | No | First eval-bench-metrics release; no recorded CI run |
| v3.10.1 | Advisory | No | No clean live-provider CI train recorded; promotion deferred |

**Promotion criteria**: Promotion from advisory to blocking requires at least one
recorded clean CI train (all fixtures pass with live providers). Until that evidence
exists, the lane remains advisory (`continue-on-error: true`).

**Credential handling**: No changes to credential handling in this release train.
API keys are never stored in repository files; they are injected at CI runtime via
GitHub Actions secrets only when `ENABLE_LIVE_LLM_TESTS=true` is set.

---

## DeepSeek (EXPERIMENTAL, v4.10.0+)

DeepSeek is supported via the standard OpenAI-compatible ChatCompletions path.
It is an **EXPERIMENTAL** preset; the preset and its defaults may change without
a stable-contract bump.

**Configuration:**

```toml
[llm]
provider = "deepseek"
model = "deepseek-v4-pro"          # default; override as needed
# base_url is auto-filled from the preset (https://api.deepseek.com)
```

| Setting | Value |
|---|---|
| API key env var | `DEEPSEEK_API_KEY` |
| Base URL (preset) | `https://api.deepseek.com` |
| Default model | `deepseek-v4-pro` |
| Fallback model (future) | `deepseek-v4-flash` |

**Key resolution order**: `DEEPSEEK_API_KEY` → `OPENAI_API_KEY` → `SAFECODE_LLM_API_KEY`.

**Advisory notes:**
- Never write `DEEPSEEK_API_KEY` to disk or commit it to the repository.
- DeepSeek V4 may return reasoning/thinking-related fields; unknown response fields
  are ignored safely by the existing parser.
- Network policy still governs whether the call is permitted.
  Set `network_enabled = true` in your config or use `sac setup --wizard` to enable it.
- Use `sac doctor` to check API key presence and static network policy verdict without
  making any network request.
- Use `SAFECODE_LIVE_SMOKE=1 sac smoke live-provider` (v4.10.4+) for an opt-in
  end-to-end connectivity check.

---

## Experimental Features

The following are not part of the supported contract and may change:

- **Prompt caching headers** (`cache_control`): Anthropic caching metadata recorded
  when present, but `cache_control` request headers are not yet sent.
- **Additional cloud providers**: only `mock`, `openai`, `openai-compatible`,
  `anthropic`, and `deepseek` are tested.
- **Provider-specific advanced options**: tool use, vision, system prompts beyond
  the SafeCode contract prompt.
- **Live CI lane blocking gate**: currently advisory; may become blocking in future.
- **Streaming fan-out mid-stream**: `FanOutLLMClient.stream_chat()` proxies to the
  primary only; mid-stream recovery to fallback is not implemented.

---

## Contract Snapshot

See `tests/snapshots/contracts/provider_contract_schema.json` for the machine-readable
contract snapshot used by `tests/test_provider_contract_snapshot.py`.
