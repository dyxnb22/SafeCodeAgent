# Interview Talking Points

**Implementation status (v1.9):** Executable contracts through v1.9 are implemented; see `.agents/context/progress.json` for live stage state.
## One-Minute Pitch

SafeCodeAgent Enterprise is a governed security engineering agent. It combines
RAG, LangGraph-style workflows, tool calling, MCP integrations, approval gates,
audit logs, rollback, and evaluation so the agent can safely handle PR security
review and vulnerability remediation instead of just answering questions.

## Why This Is Better Than A RAG Chatbot

RAG is one component, not the product. The product value is the workflow:
retrieve evidence, reason over code and policy, call tools, propose a fix,
validate it, pause for approval at risk boundaries, and leave traceable proof.

## Technical Points To Explain

- RAG design: chunking, metadata filters, hybrid search, reranking, citations,
  stale-document handling, and permission-aware retrieval.
- LangGraph design: state graph, checkpointing, conditional edges, retries, and
  human interrupts.
- Multi-agent discipline: separate roles only where outputs differ, such as
  security analysis, code fix proposal, policy review, validation, and report.
- Tool safety: tool schemas and approval flags are local code contracts, not
  model-provided fields.
- MCP safety: server output is untrusted; write tools use proposal, approval,
  single-use grants, and audit.
- Guardrails: structured output validation, prompt-injection tests, redaction,
  network allowlists, RBAC, and fail-closed behavior.
- Observability: traces for nodes, tool calls, retrieval evidence, approvals,
  cost, latency, failure categories, and validation.
- Evaluation: ratchet baselines, safety fixtures, retrieval recall, pass@1,
  live provider smoke, and dashboards.

## Strong Architecture Sentence

The model can suggest actions, but deterministic local and enterprise policy
decides what can read, write, call networks, execute commands, push branches, or
create PRs.

## Tradeoffs

- Prefer workflow determinism over free-form autonomous agents.
- Prefer explicit approval states over hidden trust.
- Prefer grounded citations over fluent but unverifiable answers.
- Prefer a small number of role agents with typed handoffs over generic
  multi-agent chatter.
- Prefer local Markdown/HTML reports first, then a web dashboard after schemas
  stabilize.
