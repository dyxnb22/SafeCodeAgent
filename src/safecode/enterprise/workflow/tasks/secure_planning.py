"""Secure implementation planning workflow helpers (v2.4.5)."""

from __future__ import annotations

import re
from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.enterprise.connectors.issue import IssueConnectorSpec, fetch_issue
from safecode.enterprise.connectors.models import IssueEvidence
from safecode.enterprise.connectors.session import get_jira_api_token, get_jira_email, get_jira_transport
from safecode.enterprise.memory.chunks import active_memory_chunks
from safecode.enterprise.memory.store import MemoryFactStore
from safecode.enterprise.rag.index_builder import build_chunks_from_manifest
from safecode.enterprise.rag.models import Citation
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.rag.source_registry import SourceType
from safecode.enterprise.workflow.state import (
    EnterpriseRunState,
    Plan,
    PlanAction,
    Proposal,
    SecurityFinding,
    Location,
)
from safecode.enterprise.workflow.types import RiskTier, TaskType

MANIFEST_REL = Path("examples/enterprise/knowledge_sources.yaml")
RAG_MAX_CITATIONS = 8

_TOKEN_PATTERNS = (
    re.compile(r"(?i)(token|session|password|credential)"),
    re.compile(r"(?i)(reuse|replay|leak)"),
)
_AUTH_PATTERNS = (
    re.compile(r"(?i)(oauth|oidc|saml|mfa)"),
    re.compile(r"(?i)(authentication|authorization)"),
)


def is_secure_planning_task(state: EnterpriseRunState) -> bool:
    return state.task_type == TaskType.secure_planning


def resolve_ticket_path(repo_root: Path, input_ref: str) -> tuple[Path, Path, str]:
    root = repo_root.resolve()
    ref = Path(input_ref)
    if ref.is_absolute():
        candidate = ref.resolve()
    else:
        candidate = (root / ref).resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("ticket path escapes repository root")
    if candidate.is_dir():
        for name in ("ticket.json", "ticket.md", "issue.json"):
            nested = candidate / name
            if nested.is_file():
                candidate = nested.resolve()
                break
        else:
            json_files = sorted(candidate.glob("*.json"))
            md_files = sorted(candidate.glob("*.md"))
            if json_files:
                candidate = json_files[0].resolve()
            elif md_files:
                candidate = md_files[0].resolve()
            else:
                raise FileNotFoundError(f"no ticket fixture in {candidate}")
    source_kind = "jira_json" if candidate.suffix.lower() == ".json" else "markdown"
    return candidate, candidate.parent, source_kind


def collect_issue(
    repo_root: Path,
    input_ref: str,
    *,
    input_kind: str = "ticket",
    extra: dict[str, str] | None = None,
) -> tuple[IssueEvidence | None, str]:
    metadata = dict(extra or {})
    if input_kind == "ticket" and metadata.get("live_jira") == "1":
        issue_key = metadata.get("issue_key", "").strip()
        base_url = metadata.get("jira_base_url", "https://example.atlassian.net")
        if issue_key:
            try:
                evidence = fetch_issue(
                    IssueConnectorSpec(
                        mode="live",
                        issue_key=issue_key,
                        api_base_url=base_url,
                    ),
                    email=get_jira_email(),
                    api_token=get_jira_api_token(),
                    transport=get_jira_transport(),
                )
                return evidence, issue_key
            except Exception:
                return None, issue_key
    try:
        fixture_path, project_root, source_kind = resolve_ticket_path(repo_root, input_ref)
    except (FileNotFoundError, ValueError):
        return None, ""
    if not fixture_path.is_file():
        return None, ""
    evidence = fetch_issue(
        IssueConnectorSpec(
            source_kind=source_kind,  # type: ignore[arg-type]
            source_path=fixture_path.name,
            project_root=str(project_root),
        )
    )
    issue_key = evidence.issue_id if evidence.issue_id != "unknown" else fixture_path.stem
    return evidence, issue_key


def retrieval_actor_scope(state: EnterpriseRunState) -> list[str]:
    return sorted(set(state.subject.permission_scopes))


def build_retrieval_queries(evidence: IssueEvidence) -> list[str]:
    queries = [
        f"secure implementation {evidence.title}",
        "architecture threat model authentication",
        "secure coding standard python",
    ]
    for label in evidence.labels:
        queries.append(f"security policy {label}")
    if evidence.body:
        queries.append(evidence.body.split(".")[0][:120])
    deduped: list[str] = []
    for query in queries:
        if query and query not in deduped:
            deduped.append(query)
    while len(deduped) < 4:
        deduped.append("secure implementation planning")
    return deduped[:4]


def retrieve_citations(state: EnterpriseRunState, evidence: IssueEvidence) -> list[Citation]:
    project_root = Path(state.repo.repo_root).resolve()
    manifest = project_root / MANIFEST_REL
    chunks = build_chunks_from_manifest(manifest, project_root)
    sac_root = project_root / ".sac"
    memory_store = MemoryFactStore(sac_root)
    chunks.extend(
        active_memory_chunks(
            memory_store,
            state.tenant_id,
            actor_scope=set(retrieval_actor_scope(state)),
        )
    )
    retriever = HybridRetriever(chunks=chunks)
    actor_scope = retrieval_actor_scope(state)
    seen: dict[str, Citation] = {}
    per_query = max(1, RAG_MAX_CITATIONS // 4)
    for query in build_retrieval_queries(evidence):
        for citation in retriever.retrieve(
            query,
            per_query,
            actor_scope,
            actor_tenant=state.tenant_id,
        ):
            seen[citation.citation_id] = citation
    return list(seen.values())[:RAG_MAX_CITATIONS]


def policy_citations(citations: list[Citation]) -> list[Citation]:
    return [
        item
        for item in citations
        if item.source_type
        in {SourceType.security_policy, SourceType.secure_coding_standard, SourceType.architecture_doc}
    ]


def code_citations(citations: list[Citation]) -> list[Citation]:
    return [item for item in citations if item.source_type == SourceType.code]


def _severity_to_risk(severity: str) -> RiskTier:
    mapping = {
        "critical": RiskTier.critical,
        "high": RiskTier.high,
        "medium": RiskTier.medium,
        "low": RiskTier.low,
        "unknown": RiskTier.medium,
    }
    return mapping.get(severity, RiskTier.medium)


def analyze_ticket_security(
    evidence: IssueEvidence,
    citations: list[Citation],
) -> tuple[list[SecurityFinding], RiskTier]:
    corpus = f"{evidence.title}\n{evidence.body}"
    findings: list[SecurityFinding] = []
    location = Location(path=f"ticket/{evidence.issue_id}", start_line=1, end_line=1, snippet_hash=evidence.evidence_id)
    if any(pattern.search(corpus) for pattern in _TOKEN_PATTERNS):
        findings.append(
            SecurityFinding(
                finding_id=f"finding-token-risk-{evidence.issue_id}",
                source="agent_analysis",
                rule_id="token-handling",
                severity=RiskTier.high,
                title="Token or credential handling risk",
                description="Ticket references token, session, or credential flows requiring hardened controls.",
                cwe="CWE-287",
                location=location,
            )
        )
    if any(pattern.search(corpus) for pattern in _AUTH_PATTERNS):
        findings.append(
            SecurityFinding(
                finding_id=f"finding-auth-scope-{evidence.issue_id}",
                source="agent_analysis",
                rule_id="auth-scope",
                severity=RiskTier.medium,
                title="Authentication scope change",
                description="Ticket touches authentication or authorization boundaries.",
                cwe="CWE-306",
                location=location,
            )
        )
    if not findings and citations:
        findings.append(
            SecurityFinding(
                finding_id=f"finding-planning-{evidence.issue_id}",
                source="agent_analysis",
                rule_id="planning-review",
                severity=_severity_to_risk(evidence.severity),
                title="Planning review required",
                description="Ticket requires secure implementation planning against cited policy.",
                location=location,
            )
        )
    tier = _severity_to_risk(evidence.severity)
    if findings:
        order = [RiskTier.low, RiskTier.medium, RiskTier.high, RiskTier.critical]
        tier = max(findings, key=lambda item: order.index(item.severity)).severity
    return findings, tier


def build_planning_plan(
    state: EnterpriseRunState,
    evidence: IssueEvidence,
    citations: list[Citation],
    findings: list[SecurityFinding],
    risk_tier: RiskTier,
) -> Plan:
    citation_ids = [item.citation_id for item in citations]
    actions: list[PlanAction] = [
        PlanAction(
            action_id="review-citations",
            title="Review cited policy and architecture constraints",
            risk_tier=risk_tier,
            requires_approval=False,
        ),
        PlanAction(
            action_id="design-secure-flow",
            title=f"Design secure flow for {evidence.title}",
            risk_tier=risk_tier,
            requires_approval=False,
        ),
        PlanAction(
            action_id="add-tests",
            title="Add security regression tests for the change",
            risk_tier=RiskTier.medium,
            requires_approval=False,
        ),
    ]
    if findings:
        actions.append(
            PlanAction(
                action_id="threat-model-update",
                title="Update threat model for identified risks",
                risk_tier=risk_tier,
                requires_approval=risk_tier in {RiskTier.high, RiskTier.critical},
            )
        )
    if state.request.extra.get("post_to_ticket") == "1":
        actions.append(
            PlanAction(
                action_id="ticket-comment-post",
                title="Post planning summary to ticket",
                risk_tier=risk_tier,
                requires_approval=True,
            )
        )
    alternatives = [
        "Defer implementation and run a focused threat-modeling session.",
        "Ship a minimal read-only prototype behind feature flags before full rollout.",
        "Reuse an existing hardened auth module instead of bespoke token handling.",
    ]
    revisit_trigger = (
        "Revisit when ticket scope changes, new auth integration is proposed, "
        "or cited policy documents are updated."
    )
    return Plan(
        plan_id=f"plan-{state.run_id}",
        summary=f"Secure implementation plan for {evidence.issue_id}",
        actions=actions,
        alternatives=alternatives,
        revisit_trigger=revisit_trigger,
        citation_ids=citation_ids,
    )


def build_ticket_comment_body(state: EnterpriseRunState, plan: Plan) -> str:
    lines = [
        "## Secure implementation plan",
        "",
        plan.summary,
        "",
        "### Actions",
    ]
    for action in plan.actions:
        lines.append(f"- {action.title}")
    if plan.alternatives:
        lines.append("")
        lines.append("### Alternatives considered")
        for alt in plan.alternatives:
            lines.append(f"- {alt}")
    if plan.revisit_trigger:
        lines.append("")
        lines.append(f"**Revisit trigger:** {plan.revisit_trigger}")
    if plan.citation_ids:
        lines.append("")
        lines.append(f"Citations: {', '.join(plan.citation_ids[:6])}")
    return redact_secrets("\n".join(lines))


def build_planning_proposals(
    state: EnterpriseRunState,
    *,
    report_ref: str,
    comment_ref: str | None,
) -> list[Proposal]:
    proposals = [
        Proposal(
            proposal_id=f"proposal-plan-{state.run_id}",
            kind="report",
            summary="Secure implementation plan report",
            ref=report_ref,
        )
    ]
    if comment_ref is not None:
        proposals.append(
            Proposal(
                proposal_id=f"proposal-ticket-comment-{state.run_id}",
                kind="ticket",
                summary="Ticket planning comment draft",
                ref=comment_ref,
            )
        )
    return proposals
