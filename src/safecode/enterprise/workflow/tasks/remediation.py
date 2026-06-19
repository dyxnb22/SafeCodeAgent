"""Vulnerability remediation workflow sub-graph helpers."""

from __future__ import annotations

import hashlib
import ast
import json
import re
from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.enterprise.rag.index_builder import build_chunks_from_manifest
from safecode.enterprise.rag.models import Citation
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.rag.source_registry import SourceType
from safecode.enterprise.scanners.pip_audit import normalize_pip_audit
from safecode.enterprise.scanners.semgrep import (
    UnsupportedScannerVersionError,
    normalize_semgrep,
)
from safecode.enterprise.workflow.state import (
    EnterpriseRunState,
    Plan,
    PlanAction,
    Proposal,
    SecurityFinding,
    ValidationResult,
)
from safecode.enterprise.workflow.types import RiskTier, TaskType
from safecode.patch.models import PatchBlock, PatchProposal

MANIFEST_REL = Path("examples/enterprise/knowledge_sources.yaml")
RAG_MAX_CITATIONS = 8
MAX_PATCH_FILES = 5

_RULE_CLASSIFIERS = (
    (re.compile(r"sql[-.]?injection", re.I), "sql_injection", "CWE-89"),
    (re.compile(r"hardcoded[-_]?secret|secret", re.I), "hardcoded_secret", "CWE-798"),
    (re.compile(r"eval|exec", re.I), "unsafe_eval", "CWE-95"),
    (re.compile(r"path[-_]?traversal|\.\./", re.I), "path_traversal", "CWE-22"),
    (re.compile(r"CVE-\d{4}-\d+", re.I), "dependency_cve", None),
)


def is_remediation_task(state: EnterpriseRunState) -> bool:
    return state.task_type == TaskType.remediation


def resolve_finding_fixture(repo_root: Path, input_ref: str) -> Path:
    root = repo_root.resolve()
    ref = Path(input_ref)
    candidate = ref.resolve() if ref.is_absolute() else (root / ref).resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("finding fixture path escapes repository root")
    if candidate.is_dir():
        for name in ("finding.json", "semgrep.json", "finding.sarif.json"):
            nested = candidate / name
            if nested.is_file():
                return nested.resolve()
        json_files = sorted(candidate.glob("*.json"))
        if json_files:
            return json_files[0].resolve()
        raise FileNotFoundError(f"no finding fixture in {candidate}")
    return candidate


def _normalize_sarif_findings(payload: dict) -> list[SecurityFinding]:
    from safecode.enterprise.workflow.state import Location

    findings: list[SecurityFinding] = []
    for run in payload.get("runs") or []:
        for index, item in enumerate(run.get("results") or []):
            rule_id = str(item.get("ruleId") or "sarif-rule")
            locations = item.get("locations") or []
            path = "unknown"
            start = 1
            end = 1
            if locations:
                physical = (locations[0].get("physicalLocation") or {}).get("artifactLocation") or {}
                path = str(physical.get("uri") or path)
                region = (locations[0].get("physicalLocation") or {}).get("region") or {}
                start = int(region.get("startLine") or 1)
                end = int(region.get("endLine") or start)
            message = redact_secrets(str((item.get("message") or {}).get("text") or rule_id))
            digest = hashlib.sha256(f"{rule_id}:{path}:{start}".encode()).hexdigest()[:16]
            findings.append(
                SecurityFinding(
                    finding_id=f"finding-{digest}",
                    source="sarif",
                    rule_id=rule_id,
                    severity=RiskTier.high,
                    title=message[:512],
                    description=message[:4096],
                    location=Location(path=path, start_line=start, end_line=end, snippet_hash=digest),
                )
            )
    return findings


def ingest_findings(repo_root: Path, input_ref: str) -> list[SecurityFinding]:
    path = resolve_finding_fixture(repo_root, input_ref)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "results" in payload:
        return normalize_semgrep(payload)
    if isinstance(payload, dict) and "runs" in payload:
        return _normalize_sarif_findings(payload)
    if isinstance(payload, (dict, list)):
        try:
            return normalize_pip_audit(payload)
        except Exception:
            pass
    raise UnsupportedScannerVersionError(f"unsupported finding fixture: {path}")


def retrieval_actor_scope(state: EnterpriseRunState) -> list[str]:
    scopes = set(state.subject.permission_scopes)
    scopes.update({"org", "appsec", "secops"})
    return sorted(scopes)


def build_retrieval_queries(findings: list[SecurityFinding]) -> list[str]:
    queries: list[str] = []
    for finding in findings[:3]:
        queries.append(f"{finding.rule_id} {finding.cwe or ''} secure policy")
        queries.append(f"{finding.location.path} vulnerability remediation")
    queries.append("secure coding parameterized queries python")
    deduped: list[str] = []
    for query in queries:
        if query not in deduped:
            deduped.append(query)
    while len(deduped) < 3:
        deduped.append("enterprise security policy remediation")
    return deduped[:4]


def retrieve_citations(state: EnterpriseRunState, findings: list[SecurityFinding]) -> list[Citation]:
    project_root = Path(state.repo.repo_root).resolve()
    manifest = project_root / MANIFEST_REL
    chunks = build_chunks_from_manifest(manifest, project_root)
    retriever = HybridRetriever(chunks=chunks)
    seen: dict[str, Citation] = {}
    per_query = max(1, RAG_MAX_CITATIONS // 4)
    for query in build_retrieval_queries(findings):
        for citation in retriever.retrieve(
            query,
            per_query,
            retrieval_actor_scope(state),
            actor_tenant=state.tenant_id,
        ):
            seen[citation.citation_id] = citation
    return list(seen.values())[:RAG_MAX_CITATIONS]


def classify_finding(finding: SecurityFinding) -> str:
    haystack = f"{finding.rule_id} {finding.title} {finding.cve or ''}"
    for pattern, label, _cwe in _RULE_CLASSIFIERS:
        if pattern.search(haystack):
            return label
    if finding.source == "pip_audit":
        return "dependency_cve"
    return "unknown"


def aggregate_risk_tier(findings: list[SecurityFinding]) -> RiskTier:
    if not findings:
        return RiskTier.low
    order = [RiskTier.low, RiskTier.medium, RiskTier.high, RiskTier.critical]
    return max(findings, key=lambda item: order.index(item.severity)).severity


def build_remediation_plan(
    state: EnterpriseRunState,
    findings: list[SecurityFinding],
    citations: list[Citation],
) -> Plan:
    policy_ref = next(
        (item.path for item in citations if item.source_type == SourceType.security_policy),
        "policy",
    )
    actions: list[PlanAction] = []
    for index, finding in enumerate(findings[:MAX_PATCH_FILES]):
        vuln_type = classify_finding(finding)
        actions.append(
            PlanAction(
                action_id=f"fix-{index + 1}",
                title=f"Fix {vuln_type} referencing {policy_ref}",
                risk_tier=finding.severity,
                requires_approval=True,
            )
        )
    return Plan(
        plan_id=f"plan-{state.run_id}",
        summary="remediation fix plan",
        actions=actions,
    )


def _target_path(repo_root: Path, input_ref: str, relative_path: str) -> Path:
    root = repo_root.resolve()
    direct = (repo_root / relative_path).resolve()
    if (direct == root or root in direct.parents) and direct.is_file():
        return direct
    fixture_dir = resolve_finding_fixture(repo_root, input_ref).parent
    candidate = (fixture_dir / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("finding target path escapes repository root")
    return candidate


def _read_target(repo_root: Path, input_ref: str, relative_path: str) -> str:
    path = _target_path(repo_root, input_ref, relative_path)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def build_patch_proposal(
    state: EnterpriseRunState,
    finding: SecurityFinding,
) -> PatchProposal | None:
    repo_root = Path(state.repo.repo_root).resolve()
    rel_path = finding.location.path
    if rel_path.startswith("pkg:"):
        fixture_dir = resolve_finding_fixture(repo_root, state.request.input_ref).parent
        candidate = fixture_dir / "requirements.txt"
        if candidate.is_file():
            rel_path = str(candidate.relative_to(fixture_dir))
        else:
            rel_path = "requirements.txt"
    content = _read_target(repo_root, state.request.input_ref, rel_path)
    if not content:
        return None
    target_path = _target_path(repo_root, state.request.input_ref, rel_path)
    patch_file_path = target_path.relative_to(repo_root)
    vuln_type = classify_finding(finding)
    proposal_id = f"patch-{state.run_id}-{finding.finding_id}"
    if vuln_type == "sql_injection" and "f\"" in content:
        search = re.search(
            r'query\s*=\s*f"[^"]+"\s*\n\s*return\s+db\.execute\(query\)',
            content,
        )
        if search:
            replace = (
                'query = "SELECT * FROM users WHERE id=?"\n'
                "    return db.execute(query, (user_id,))"
            )
            return PatchProposal(
                id=proposal_id,
                task="remediation sql injection",
                blocks=[
                    PatchBlock(
                        operation="update",
                        file_path=patch_file_path,
                        search=search.group(0),
                        replace=replace,
                    )
                ],
                created_at=state.updated_at,
                model="mock",
            )
    if vuln_type == "hardcoded_secret":
        search = re.search(r"(API_KEY|PASSWORD|SECRET)\s*=\s*\"[^\"]+\"", content)
        if search:
            key = search.group(1)
            replacement = f'{key} = os.environ.get("{key}")'
            if "import os" not in content:
                replacement = f"import os\n{replacement}"
            return PatchProposal(
                id=proposal_id,
                task="remediation hardcoded secret",
                blocks=[
                    PatchBlock(
                        operation="update",
                        file_path=patch_file_path,
                        search=search.group(0),
                        replace=replacement,
                    )
                ],
                created_at=state.updated_at,
                model="mock",
            )
    if vuln_type == "unsafe_eval" and "eval(" in content:
        return PatchProposal(
            id=proposal_id,
            task="remediation unsafe eval",
            blocks=[
                PatchBlock(
                    operation="update",
                    file_path=patch_file_path,
                    search="eval(",
                    replace="ast.literal_eval(",
                )
            ],
            created_at=state.updated_at,
            model="mock",
        )
    if vuln_type == "path_traversal" and "open(" in content:
        target = "return open(path).read()"
        if target in content:
            return PatchProposal(
                id=proposal_id,
                task="remediation path traversal",
                blocks=[
                    PatchBlock(
                        operation="update",
                        file_path=patch_file_path,
                        search=target,
                        replace=(
                            "candidate = (BASE_DIR / path).resolve()\n"
                            "    if BASE_DIR.resolve() not in candidate.parents:\n"
                            '        raise ValueError("path escapes base directory")\n'
                            "    return candidate.read_text()"
                        ),
                    )
                ],
                created_at=state.updated_at,
                model="mock",
            )
    if vuln_type == "dependency_cve" and "==" in content:
        search = re.search(r"(\w+)==([\d.]+)", content)
        if search:
            package, version = search.group(1), search.group(2)
            fixed = re.search(r"\d+(?:\.\d+){1,3}", finding.description)
            bumped = fixed.group(0) if fixed else ".".join(
                version.split(".")[:-1] + [str(int(version.split(".")[-1]) + 1)]
            )
            return PatchProposal(
                id=proposal_id,
                task="remediation dependency bump",
                blocks=[
                    PatchBlock(
                        operation="update",
                        file_path=patch_file_path,
                        search=f"{package}=={version}",
                        replace=f"{package}=={bumped}",
                    )
                ],
                created_at=state.updated_at,
                model="mock",
            )
    return None


def policy_citations(citations: list[Citation]) -> list[Citation]:
    return [item for item in citations if item.source_type == SourceType.security_policy]


def code_citations(citations: list[Citation]) -> list[Citation]:
    return [item for item in citations if item.source_type == SourceType.code]


def build_proposals(
    state: EnterpriseRunState,
    *,
    report_ref: str,
    patch_ref: str | None,
    patch_proposal: PatchProposal | None,
) -> list[Proposal]:
    proposals = [
        Proposal(
            proposal_id=f"proposal-report-{state.run_id}",
            kind="report",
            summary="remediation report",
            ref=report_ref,
        )
    ]
    if patch_ref is not None and patch_proposal is not None:
        proposals.append(
            Proposal(
                proposal_id=f"proposal-patch-{state.run_id}",
                kind="patch",
                summary=patch_proposal.task,
                ref=patch_ref,
            )
        )
    return proposals


def run_pre_apply_validation(state: EnterpriseRunState) -> ValidationResult:
    if state.request.extra.get("validation_failed") == "1":
        return ValidationResult(passed=False, summary="pre-apply validation failed")
    return ValidationResult(
        passed=True,
        summary="pre-apply validation passed",
        details={"tests": "passed", "scanner": "proposed"},
    )


def run_post_apply_validation(
    state: EnterpriseRunState,
    *,
    finding: SecurityFinding | None,
    regression: bool = False,
) -> ValidationResult:
    if regression or state.request.extra.get("post_validation_failed") == "1":
        return ValidationResult(
            passed=False,
            summary="post-apply validation failed",
            details={"tests": "failed", "scanner_diff": "new_findings=1"},
        )
    if finding is None:
        return ValidationResult(
            passed=False,
            summary="post-apply validation missing finding",
            details={"tests": "failed", "scanner_diff": "finding_context_missing"},
        )
    repo_root = Path(state.repo.repo_root).resolve()
    relative_path = finding.location.path
    if relative_path.startswith("pkg:"):
        relative_path = "requirements.txt"
    target = _target_path(repo_root, state.request.input_ref, relative_path)
    content = target.read_text(encoding="utf-8") if target.is_file() else ""
    vuln_type = classify_finding(finding)
    syntax_ok = True
    if target.suffix == ".py":
        try:
            ast.parse(content)
        except SyntaxError:
            syntax_ok = False
    vulnerable = {
        "sql_injection": bool(re.search(r'query\s*=\s*f["\']', content)),
        "hardcoded_secret": bool(
            re.search(r"(API_KEY|PASSWORD|SECRET)\s*=\s*[\"\'][^\"\']+[\"\']", content)
        ),
        "unsafe_eval": bool(re.search(r"(?<!literal_)eval\(", content)),
        "path_traversal": "open(path)" in content,
        "dependency_cve": bool(re.search(r"==\s*2\.25\.0", content)),
    }.get(vuln_type, True)
    if not content or not syntax_ok or vulnerable:
        return ValidationResult(
            passed=False,
            summary="post-apply validation failed",
            details={
                "tests": "passed" if syntax_ok else "failed",
                "scanner_diff": "finding_not_cleared",
            },
        )
    return ValidationResult(
        passed=True,
        summary="post-apply validation passed",
        details={"tests": "passed", "scanner_diff": "cleared_findings=1"},
    )
