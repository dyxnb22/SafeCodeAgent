# Observability And Evaluation

**Implementation status (v1.9):** Executable contracts through v1.9 are implemented; see `.agents/context/progress.json` for live stage state.
## Observability Goals

Enterprise users need to answer:
- What did the agent do?
- Which evidence did it use?
- Which policy allowed or blocked an action?
- Who approved the risky step?
- What changed?
- What validation passed?
- How much did it cost?
- Where did it fail?

## Trace Events

Record events for:
- workflow start/end
- node start/end
- model request lifecycle
- structured output validation
- retrieval query and selected citations
- tool call preview, approval, execution, and result
- command/scanner validation
- policy block
- human decision
- final report generation

Trace payloads must be redacted and bounded. Raw prompts, secrets, and full
source files should not be emitted by default.

## Run Timeline

The first dashboard can be Markdown or HTML. Required sections:
- request summary and final outcome
- risk tier and approval summary
- workflow timeline
- cited evidence
- proposed changes
- validation commands and scanner results
- cost and token summary
- safety invariants
- failure or retry details

## Evaluation Strategy

Reuse SafeCodeAgent's discipline:
- deterministic local tests use the mock provider
- live provider tests are opt-in
- fixture baselines ratchet after evidence
- safety regressions block promotion
- transcripts are redacted and stored only when requested

## Eval Suites

Add Enterprise suites:
- PR security review
- vulnerability remediation
- policy retrieval recall
- code localization
- prompt-injection resistance
- MCP/tool classification attacks
- approval and RBAC enforcement
- GitHub write dry-run and approval behavior
- scanner finding normalization
- report citation grounding

## Metrics

Recommended metrics:
- task success
- pass@1 and pass@N
- policy recall
- citation grounding accuracy
- relevant-file recall and precision
- validation pass rate
- unauthorized mutation count
- blocked unsafe action count
- approval pause correctness
- cost per run
- latency per node
- retry count and failure category

## Release Evidence

A release should include:
- pytest summary
- Enterprise eval dashboard
- safety invariant summary
- retrieval evaluation snapshot
- live provider smoke result if enabled
- known limitations and deferred claims
