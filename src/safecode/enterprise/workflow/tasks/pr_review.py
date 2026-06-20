"""PR security review workflow sub-graph helpers."""

from __future__ import annotations

import re
from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.enterprise.connectors.github_pr import PullRequestConnectorSpec, fetch_pr
from safecode.enterprise.connectors.models import PullRequestEvidence
from safecode.enterprise.rag.index_builder import build_chunks_from_manifest
from safecode.enterprise.rag.models import Citation
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.rag.source_registry import SourceType
from safecode.enterprise.workflow.state import (
    EnterpriseRunState,
    Location,
    Plan,
    PlanAction,
    Proposal,
    SecurityFinding,
)
from safecode.enterprise.workflow.types import RiskTier, TaskType

MANIFEST_REL = Path("examples/enterprise/knowledge_sources.yaml")
RAG_MAX_CITATIONS = 8

_SQL_PATTERNS = (
    re.compile(r'f["\']SELECT', re.IGNORECASE),
    re.compile(r"\+.*SELECT", re.IGNORECASE),
    re.compile(r"WHERE\s+id=\{", re.IGNORECASE),
    re.compile(r"execute\(f", re.IGNORECASE),
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|password|secret)\s*=\s*['\"][^'\"]+['\"]"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)
_DESER_PATTERNS = (
    re.compile(r"pickle\.loads\("),
    re.compile(r"yaml\.load\([^,)]*\)"),
    re.compile(r"marshal\.loads\("),
)
_CVE_PATTERN = re.compile(r"CVE-\d{4}-\d+", re.IGNORECASE)


def is_pr_review_task(state: EnterpriseRunState) -> bool:
    return state.task_type == TaskType.pr_review


def resolve_fixture_path(repo_root: Path, input_ref: str) -> tuple[Path, Path]:
    """Return fixture file path and connector project root."""
    root = repo_root.resolve()
    ref = Path(input_ref)
    if ref.is_absolute():
        candidate = ref.resolve()
        project_root = candidate.parent
    else:
        candidate = (root / ref).resolve()
        project_root = root
    if root not in candidate.parents and candidate != root:
        raise ValueError("PR fixture path escapes repository root")
    if candidate.is_dir():
        for name in ("pr.json", "fixture.json"):
            nested = candidate / name
            if nested.is_file():
                return nested.resolve(), candidate.resolve()
        json_files = sorted(candidate.glob("*.json"))
        if json_files:
            return json_files[0].resolve(), candidate.resolve()
        raise FileNotFoundError(f"no PR fixture JSON in {candidate}")
    return candidate, project_root


def collect_pull_request(
    repo_root: Path,
    input_ref: str,
    *,
    input_kind: str = "pr_fixture",
    extra: dict[str, str] | None = None,
    installation_id: str | None = None,
) -> PullRequestEvidence | None:
    from safecode.enterprise.connectors.session import get_github_access_token, get_github_transport

    metadata = dict(extra or {})
    if input_kind == "pr_live":
        owner = metadata.get("owner", "").strip()
        repo = metadata.get("repo", "").strip()
        try:
            pr_number = int(metadata.get("pr_number") or 0)
        except ValueError:
            pr_number = 0
        if owner and repo and pr_number > 0:
            try:
                return fetch_pr(
                    PullRequestConnectorSpec(
                        mode="live",
                        owner=owner,
                        repo=repo,
                        pr_number=pr_number,
                        installation_id=installation_id,
                    ),
                    access_token=get_github_access_token(),
                    transport=get_github_transport(),
                )
            except Exception:
                return None
    try:
        fixture_path, project_root = resolve_fixture_path(repo_root, input_ref)
    except (FileNotFoundError, ValueError):
        return None
    if not fixture_path.is_file():
        return None
    return fetch_pr(
        PullRequestConnectorSpec(
            mode="fixture",
            fixture_path=fixture_path.name,
            project_root=str(project_root),
        )
    )


def retrieval_actor_scope(state: EnterpriseRunState) -> list[str]:
    return sorted(set(state.subject.permission_scopes))


def build_retrieval_queries(evidence: PullRequestEvidence) -> list[str]:
    queries: list[str] = []
    for hunk in evidence.hunks:
        queries.append(f"sql injection security {hunk.file_path}")
        if hunk.patch:
            queries.append(f"{hunk.file_path} vulnerability patch review")
    queries.append("secure coding parameterized sql python")
    queries.append("python application code security review")
    deduped: list[str] = []
    for query in queries:
        if query not in deduped:
            deduped.append(query)
    while len(deduped) < 4:
        deduped.append("python application code security review")
    return deduped[:4]


def retrieve_citations(state: EnterpriseRunState, evidence: PullRequestEvidence) -> list[Citation]:
    project_root = Path(state.repo.repo_root).resolve()
    manifest = project_root / MANIFEST_REL
    chunks = build_chunks_from_manifest(manifest, project_root)
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


def _patch_text(evidence: PullRequestEvidence) -> str:
    return "\n".join(hunk.patch for hunk in evidence.hunks)


def _finding_id(rule_id: str, file_path: str, start_line: int) -> str:
    return f"finding-{rule_id}-{file_path}-{start_line}".replace("/", "-")


def detect_findings(evidence: PullRequestEvidence) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    corpus = _patch_text(evidence)
    title_labels = " ".join([evidence.title, *evidence.labels])

    for hunk in evidence.hunks:
        patch = hunk.patch
        location = Location(
            path=hunk.file_path,
            start_line=hunk.start_line,
            end_line=hunk.end_line,
            snippet_hash=hunk.hunk_id,
        )
        if any(pattern.search(patch) for pattern in _SQL_PATTERNS):
            findings.append(
                SecurityFinding(
                    finding_id=_finding_id("sql-injection", hunk.file_path, hunk.start_line),
                    source="agent_analysis",
                    rule_id="sql-injection",
                    severity=RiskTier.high,
                    title="Possible SQL injection",
                    description="User-controlled input appears in SQL string construction.",
                    cwe="CWE-89",
                    location=location,
                )
            )
        if any(pattern.search(patch) for pattern in _SECRET_PATTERNS):
            findings.append(
                SecurityFinding(
                    finding_id=_finding_id("hardcoded-secret", hunk.file_path, hunk.start_line),
                    source="agent_analysis",
                    rule_id="hardcoded-secret",
                    severity=RiskTier.critical,
                    title="Hardcoded secret",
                    description="A credential or secret literal was added in the diff.",
                    cwe="CWE-798",
                    location=location,
                )
            )
        if any(pattern.search(patch) for pattern in _DESER_PATTERNS):
            findings.append(
                SecurityFinding(
                    finding_id=_finding_id("insecure-deserialization", hunk.file_path, hunk.start_line),
                    source="agent_analysis",
                    rule_id="insecure-deserialization",
                    severity=RiskTier.high,
                    title="Insecure deserialization",
                    description="Unsafe deserialization API used on untrusted input.",
                    cwe="CWE-502",
                    location=location,
                )
            )

    if _CVE_PATTERN.search(corpus) or _CVE_PATTERN.search(title_labels):
        match = _CVE_PATTERN.search(corpus) or _CVE_PATTERN.search(title_labels)
        cve = match.group(0).upper() if match else "CVE-UNKNOWN"
        findings.append(
            SecurityFinding(
                finding_id=_finding_id("dependency-cve", "requirements", 1),
                source="agent_analysis",
                rule_id="dependency-cve",
                severity=RiskTier.high,
                title="Dependency introduces CVE",
                description=f"Diff references {cve}; review advisory and upgrade path.",
                cve=cve,
                location=Location(path="requirements.txt", start_line=1, end_line=1, snippet_hash="cve"),
            )
        )

    return findings


def aggregate_risk_tier(findings: list[SecurityFinding]) -> RiskTier:
    if not findings:
        return RiskTier.low
    order = [RiskTier.low, RiskTier.medium, RiskTier.high, RiskTier.critical]
    return max(findings, key=lambda item: order.index(item.severity)).severity


def analyze_pr_security(
    evidence: PullRequestEvidence,
    citations: list[Citation],
) -> tuple[list[SecurityFinding], RiskTier]:
    _ = citations
    findings = detect_findings(evidence)
    return findings, aggregate_risk_tier(findings)


def build_pr_plan(state: EnterpriseRunState, findings: list[SecurityFinding], risk_tier: RiskTier) -> Plan:
    actions: list[PlanAction] = []
    if findings:
        actions.append(
            PlanAction(
                action_id="pr-comment-draft",
                title="Draft PR review comment",
                risk_tier=risk_tier,
                requires_approval=False,
            )
        )
    if state.request.input_kind == "pr_live" and findings:
        actions.append(
            PlanAction(
                action_id="pr-comment-post",
                title="Post PR review comment",
                risk_tier=risk_tier,
                requires_approval=True,
            )
        )
    if risk_tier in {RiskTier.high, RiskTier.critical}:
        actions.append(
            PlanAction(
                action_id="security-escalation",
                title="Escalate high-risk finding",
                risk_tier=risk_tier,
                requires_approval=True,
            )
        )
    return Plan(
        plan_id=f"plan-{state.run_id}",
        summary="PR security review action plan",
        actions=actions,
    )


def build_comment_body(findings: list[SecurityFinding], risk_tier: RiskTier) -> str:
    if not findings:
        return "No security findings detected in this change set."
    lines = [
        "## Security review",
        "",
        f"Overall risk: **{risk_tier.value}**",
        "",
    ]
    for finding in findings:
        lines.append(
            f"- **{finding.title}** (`{finding.rule_id}`) at "
            f"`{finding.location.path}:{finding.location.start_line}`"
        )
    return redact_secrets("\n".join(lines))


def build_pr_proposals(
    state: EnterpriseRunState,
    *,
    report_ref: str,
    comment_ref: str | None,
) -> list[Proposal]:
    proposals = [
        Proposal(
            proposal_id=f"proposal-report-{state.run_id}",
            kind="report",
            summary="PR security review report",
            ref=report_ref,
        )
    ]
    if comment_ref is not None:
        proposals.append(
            Proposal(
                proposal_id=f"proposal-comment-{state.run_id}",
                kind="comment",
                summary="PR review comment draft",
                ref=comment_ref,
            )
        )
    return proposals


def policy_citations(citations: list[Citation]) -> list[Citation]:
    return [item for item in citations if item.source_type == SourceType.security_policy]


def code_citations(citations: list[Citation]) -> list[Citation]:
    return [item for item in citations if item.source_type == SourceType.code]
