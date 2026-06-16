# SafeCode Agent — Resume Bullets and Interview Notes

## Resume Bullet Points

Choose 3–4 that match the role:

**Concise (1 line):**
> Built SafeCode Agent — a safety-first local AI coding agent in Python with
> policy-gated writes, checkpointed edits, rollback, audit logs, MCP tool
> integration, multi-provider LLM support, and a live evaluation harness.

**Engineering depth emphasis:**
> Designed and implemented a terminal AI coding agent in Python (~6,000 LOC,
> 5,500+ tests) with a structural approval gate that prevents prompt-injected
> writes, a SHA-256 hash-chain audit log, per-write checkpoint/rollback, 17
> stable public contracts with snapshot tests, and a live eval harness across
> 5 real coding tasks.

**Safety/security emphasis:**
> Built the safety layer for a local AI coding agent: policy-gated command
> execution (3 presets, project config can only tighten), tamper-evident
> append-only audit log, single-use MCP write approval grants stored outside
> the project root, and a semi-annual threat model review covering prompt
> injection, path traversal, and sandbox escape.

**Evaluation emphasis:**
> Built a live evaluation harness for an AI coding agent: 5 real coding
> fixtures (Python add function, fix failing test, rename refactor, Go HTTP
> handler, TypeScript type error), ratchet baseline that prevents regression,
> advisory CI job, and a golden demo with a reproducible bug-to-tested-commit
> transcript.

---

## Interview Q&A

### "Walk me through the project."

SafeCode Agent is a terminal coding agent I built from scratch in Python.
The core insight is that most coding agent demos focus on what the model can
do, but don't address what happens when the model is wrong or confused.

I built the safety layer first: every file write goes through a `ToolCallGate`
that checks policy and requires user approval before touching any file. That
gate is structural Python code — not a prompt instruction — so it cannot be
bypassed by prompt injection. Every write then gets a checkpoint (sha256
backup) and an append-only audit log with a hash chain, so you can verify
nothing was tampered with.

The agent supports Anthropic, OpenAI-compatible providers, and a mock mode
that makes all tests pass without any API key. I also built a live eval
harness with 5 real coding tasks that measures success rate, tool calls,
and redundant reads — so prompt changes are measurable, not just faith.

### "What was the hardest part?"

Two things:

First, the approval gate. It sounds simple — "ask before writing" — but
the hard part is making it apply to every write path consistently: native
tools, MCP write tools, GitHub tools, sandbox execution. I solved this with
`ToolCallGate`, a single structural check that every write path must go
through, with snapshot tests to verify the invariants.

Second, the MCP write approval flow. MCP servers return arbitrary content,
and that content feeds directly into `execute_granted_write`. A malicious
or compromised server could try to inject content that triggers an unintended
write. My design: the approval grant is stored outside the project root
(so the project can't forge one), it's single-use (no replay), and the
classification gate is based on static local schema, not server-supplied
metadata.

### "How is this different from Claude Code or opencode?"

SafeCode Agent's design priority is reversibility and auditability.
Claude Code is a great product but it's designed for speed and breadth —
it has more integrations, more IDE support, and Anthropic's model quality.

Where SafeCode is different:
- Every write is checkpointed and you can roll back the entire session
  atomically with `sac rollback --session <id>`.
- The audit log is a tamper-evident hash chain, not just a history.
- There's a structural approval gate — not just a trust mode — that
  cannot be bypassed by prompt injection.
- The mock provider lets all 5,500+ tests pass without a network connection.
- I built a live eval harness that actually measures quality.

The trade-off is it's terminal-only and more opinionated about the approval
flow. That's a feature for codebases where accidental writes are costly.

### "What are the stable contracts?"

I defined 17 public contracts in `docs/public-contracts.md` with snapshot
tests. A stable contract means: the CLI flag, JSON schema, and invariants
will not change without a major version bump. Examples:
- The CLI JSON envelope (every `sac --json` command uses the same `CLIJSONResponse` shape).
- The audit event hash-chain invariant (append-only JSONL, each event hashes the previous).
- The sandbox execution lifecycle (proposal → approval → claim → execute, Noop default).
- The 7 native tool schemas (read_file, list_files, search_files, grep_files, edit_file, write_file, run_command).

At v6.0.0 I'm promoting trust mode schema and session rollback to stable contracts.

### "How do you test it?"

5,500+ tests across pytest. Key test types:
- **Contract snapshot tests**: JSON schemas are pinned; if a field changes, the test fails.
- **Security eval tests**: `tests/test_sandbox_execution_security_evals.py` — 82 tests
  verifying that Docker never gets `--privileged`, env values never leak into argv, etc.
- **Policy tests**: 75 tests verifying that project config can only tighten policy, never loosen.
- **Live eval harness**: 5 real coding tasks run against a live provider (gated by env var).
- **Golden demo test**: `test_golden_demo.py` verifies the fixture starts broken and can be fixed.

All tests pass without an API key. The live eval is advisory CI gated by `ENABLE_LIVE_LLM_TESTS`.

### "What would you do differently?"

If I were starting again I'd define the public contracts earlier. I ended
up with ~45 versions before the first contract cut (v5.0), and some surfaces
had to be refactored to be snapshot-testable. Defining stable contracts at
v2.0 would have forced cleaner interfaces earlier.

I'd also build the live eval harness earlier. Right now I have 5,500+ tests
proving the loop architecture is correct, but the prompt quality improvement
(v5.6.0) was added after all the architecture work. Starting with live eval
would have made the prompt-quality feedback loop faster.

---

## One-Paragraph Project Summary (for written applications)

SafeCode Agent is a safety-first local AI coding agent I built in Python.
The core design challenge is making LLM-driven code edits safe: the agent
proposes a diff, the user reviews it, and only after explicit approval does
the agent write any file — with a sha256 checkpoint and an append-only
hash-chain audit log. The tool supports Anthropic, OpenAI-compatible
providers, and DeepSeek, with a mock provider for keyless testing (all
5,500+ tests pass without a network connection). I defined 17 stable public
contracts with snapshot tests, built an MCP tool integration with per-server
scope control and single-use write approval grants, added context compaction
for long sessions, and a live evaluation harness with 5 real coding fixtures
and a ratchet baseline. The project has no auto-apply and no auto-commit —
every mutation is gated, checkpointed, and rollback-able.
