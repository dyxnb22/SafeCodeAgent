# Product Vision

**Implementation status (v1.9):** Executable contracts through v1.9 are implemented; see `.agents/context/progress.json` for live stage state.
## Positioning

SafeCodeAgent Enterprise is an enterprise security engineering agent platform.
It helps teams investigate security findings, review risky pull requests,
retrieve internal policy context, propose fixes, run validation, and produce an
auditable report or PR.

The product should be presented as an evolution of SafeCodeAgent, not a rewrite.
SafeCodeAgent is the finished local safety kernel. Enterprise adds knowledge,
workflow orchestration, integrations, approvals, and observability around that
kernel.

## Target Users

- Application security engineers triaging SAST, dependency, secrets, and policy
  findings.
- Platform engineering teams building governed AI workflows for developers.
- Engineering managers who need auditable evidence for secure SDLC processes.
- Developers who want actionable fixes instead of generic security reports.

## Core Scenarios

1. PR security review: analyze changed files, retrieve relevant company policy,
   detect risky patterns, produce a severity-ranked report, and optionally draft
   a patch.
2. Vulnerability remediation: ingest a SAST finding, locate vulnerable code,
   retrieve historical fixes and secure coding rules, propose a minimal patch,
   run tests/scanners, and request approval.
3. Secure implementation planning: turn a Jira ticket or product requirement
   into a threat-aware implementation plan with code references and test tasks.
4. Incident or regression analysis: use logs, recent commits, runbooks, and
   repo context to generate a remediation path while preserving audit evidence.
5. Compliance evidence: export who approved what, which policies were cited,
   what tools ran, what changed, and which validation passed.

## Differentiators

- Safety-first execution: model suggestions never directly mutate state.
- Enterprise workflow orientation: LangGraph-style state, retries, approvals,
  and resumability instead of one-shot chat.
- Grounded security context: RAG is used to retrieve policies and code evidence,
  not to produce vague answers.
- Tool governance: MCP and native tools share approval, audit, redaction, and
  permission contracts.
- Measurable quality: eval fixtures, live provider smoke tests, retrieval
  precision, safety invariants, and trace dashboards.

## Non-Goals For Early Phases

- Do not build a generic knowledge-base chatbot.
- Do not auto-merge, auto-deploy, or auto-push to protected branches.
- Do not make archive or legacy docs primary context.
- Do not promise complete sandbox containment across all hosts; keep containment
  claims explicit and evidence-based.
- Do not add multi-agent roles unless they own a clear responsibility and output
  contract.
