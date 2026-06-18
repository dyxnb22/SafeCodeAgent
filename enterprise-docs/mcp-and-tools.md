# MCP And Tool Integration

## Principle

Tools are capabilities, not trust. Native tools and MCP connectors must share
the same local governance model: static classification, policy checks, redacted
outputs, approval gates, and audit events.

## Tool Classes

- read-only local tools: file read, search, symbol lookup, repo map
- local write tools: patch proposal, file write, formatting
- command tools: tests, linters, scanners, build commands
- network read tools: GitHub PR read, Jira issue read, document search
- network write tools: branch push, PR creation, ticket comments, CI triggers
- admin tools: policy changes, connector configuration, credential updates

## Required Metadata

Each tool should declare:
- name and version
- input schema
- output schema
- permission category
- approval tier
- audit event type
- network requirement
- dry-run support
- redaction policy
- tenant/project boundary rules

## MCP Rules

- MCP server-provided classifications are ignored for security decisions.
- Unknown tools default to blocked or approval-required.
- Read-only MCP output is still untrusted content and may contain prompt
  injection.
- Write-classified MCP tools require proposal, preview, approval, single-use
  grant, execution, and audit.
- Output size limits and redaction apply before model context.
- MCP errors must not echo raw secrets or large call arguments.

## GitHub And PR Workflows

Preserve the existing SafeCodeAgent invariants:
- never push to protected trunk branches such as `main`, `master`, or `trunk`
- branch pushes and PR creation require human approval
- dry-run validates and previews without network calls
- PR bodies include audit references
- subprocess calls use argv lists, not shell strings
- branch names are validated
- network must be explicitly enabled and allowlisted

## Scanner Tools

Scanner integrations should be split into:
- local scanner runs, such as Semgrep or dependency audit
- imported scanner findings, such as SAST JSON
- networked enterprise scanner APIs

Scanner outputs become evidence, not instructions. Findings should be normalized
into typed models before reaching an agent.
