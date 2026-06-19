# Security Governance

**Implementation status (v1.9):** Executable contracts through v1.9 are implemented; see `.agents/context/progress.json` for live stage state.
## Core Rule

The model can recommend; policy decides.

All Enterprise development must preserve SafeCodeAgent's structural boundary:
model output cannot directly read disallowed data, mutate files, execute
commands, call networks, push branches, create PRs, approve memory, or lower
safety policy.

## Policy Layers

Recommended precedence:
1. organization policy
2. user policy
3. project policy
4. environment variables
5. workflow-specific constraints

Lower layers may add restrictions but cannot weaken higher-layer safety.

## RBAC

Define roles for:
- viewer: read reports and allowed evidence
- developer: run local read tools and request fixes
- security reviewer: approve security reports and low-risk patches
- maintainer: approve repo writes and PR creation
- platform admin: configure connectors, policies, and credentials

RBAC should be checked before tool execution and before retrieval access.

## Approval Tiers

Suggested tiers:
- AUTO: read-only local context, safe search, static analysis summaries
- CONFIRM: local patch proposal, test commands, non-sensitive scanner runs
- GATE: file writes, high-risk commands, network writes, branch push, PR
  creation, connector configuration, policy changes, secret-bearing actions
- BLOCK: protected branch push, project config lowering safety, root escape,
  secret exfiltration, unallowlisted network, unknown dangerous command

Trust modes may reduce prompts for AUTO/CONFIRM but must not bypass GATE or
BLOCK.

## Audit Requirements

Audit events should cover:
- workflow start/end
- retrieval source selection
- model calls and structured output validation failures
- tool calls and redacted observations
- approval decisions
- patch proposals and applications
- command execution
- branch push and PR creation
- rollback or compensation actions
- policy blocks

Hash-chain audit and external anchors should remain the default local integrity
model.

## Prompt Injection Controls

- Retrieved documents, issue text, PR comments, scanner output, and MCP output
  are untrusted content.
- System and developer instructions must separate content from instructions.
- Tool authorization cannot be changed by retrieved text.
- Add explicit fixtures where retrieved docs ask the agent to ignore policy,
  reveal secrets, or execute commands.

## Secrets And PII

- Skip secret-like files by default.
- Redact secrets before model context, traces, transcripts, reports, and eval
  artifacts.
- Do not store API keys in project config.
- Debug bundles should exclude project source unless explicitly requested and
  approved.
- Trace exporters and telemetry remain disabled by default.

## Sandbox And Network

- Network is disabled by default.
- Provider and connector hosts require allowlists.
- Sandbox execution requires proposal, preflight, approval, single-use claim,
  execution, and result record.
- No sandbox backend should silently degrade to unconstrained execution.
