# RAG And Context Design

## Purpose

RAG should make security decisions grounded and auditable. It should not be a
general chat layer.

Primary retrieval targets:
- organization security policies
- secure coding standards
- architecture and API docs
- project README and design notes
- code chunks and symbol references
- historical vulnerabilities and fixes
- scanner findings and dependency metadata
- incident runbooks and postmortems

## Retrieval Pipeline

1. Source registration: define source type, owner, permission scope, refresh
   cadence, and parser.
2. Chunking: use code-aware and document-aware chunkers; keep stable chunk ids.
3. Indexing: maintain keyword index, embedding index, metadata store, and
   optional import/symbol graph.
4. Query planning: rewrite task into targeted retrieval queries.
5. Hybrid search: combine keyword, semantic, git recency, pinned files, and
   metadata filters.
6. Reranking: apply reranker when candidate count is high or policy evidence is
   ambiguous.
7. Citation packing: include source path, line range, source type, score,
   selection reason, permission verdict, and freshness.
8. Context budget packing: fit evidence into model window with truncation notes.

## Reused SafeCodeAgent Ideas

- Keep a hard context budget and report truncation decisions.
- Use selection reasons so the agent and user can understand why a source was
  included.
- Redact secrets before indexing output enters model context.
- Let project config lower budgets but not raise beyond trusted policy.
- Approved memory facts can be injected; pending facts cannot.

## Enterprise Additions

- Permission-aware retrieval: a user or run can only retrieve sources allowed by
  policy.
- Freshness tracking: policy and runbook citations should indicate stale or
  superseded content.
- Retrieval evals: measure policy recall, code localization, citation
  grounding, and false-positive evidence.
- Prompt-injection resistance: retrieved text is content, not instruction.
- Tenant isolation: indexes and caches cannot mix organizations.

## Citation Object

Recommended fields:

```json
{
  "source_id": "policy-secure-sql-001",
  "source_type": "security_policy",
  "path": "policies/sql-injection.md",
  "start_line": 12,
  "end_line": 44,
  "score": 0.82,
  "selection_reason": "policy metadata matched: sql-injection; semantic 0.78",
  "permission_verdict": "allowed",
  "freshness": "current",
  "hash": "sha256:..."
}
```

## Eval Fixtures

Add fixtures for:
- retrieving the correct policy for a vulnerability class
- finding vulnerable code and related tests
- rejecting prompt-injection instructions inside retrieved docs
- handling stale policy docs
- citing historical fixes without copying old code blindly
- staying inside context budget while preserving required evidence
