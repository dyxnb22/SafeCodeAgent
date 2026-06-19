"""Enterprise retrieval evaluation runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from safecode.enterprise.eval.cases import EvaluationCase, EvaluationResult
from safecode.enterprise.rag.index_builder import build_chunks_from_manifest
from safecode.enterprise.rag.retriever import HybridRetriever, RetrievalFilters
from safecode.enterprise.rag.source_registry import SourceType
from safecode.enterprise.workflow.contracts import NodeCost, RunCosts


def _build_filters(raw_filters: dict[str, Any] | None) -> RetrievalFilters | None:
    if not raw_filters:
        return None
    source_types = raw_filters.get("source_types")
    parsed_types = None
    if isinstance(source_types, list):
        parsed_types = [SourceType(item) for item in source_types]
    return RetrievalFilters(
        source_types=parsed_types,
        path_prefixes=raw_filters.get("path_prefixes"),
        cwe_tags=raw_filters.get("cwe_tags"),
        pinned_paths=raw_filters.get("pinned_paths"),
    )


def run_retrieval_evaluation(
    case: EvaluationCase,
    manifest_path: Path,
    project_root: Path,
) -> EvaluationResult:
    if case.query is None:
        return EvaluationResult(
            case_id=case.case_id,
            suite=case.suite,
            passed=False,
            notes="retrieval case missing query",
        )
    chunks = build_chunks_from_manifest(manifest_path, project_root)
    retriever = HybridRetriever(chunks=chunks)
    filters = _build_filters(case.filters or None)
    citations = retriever.retrieve(
        case.query,
        case.k,
        case.actor_scope,
        actor_tenant=case.actor_tenant,
        filters=filters,
    )
    retrieved = [item.source_id for item in citations]
    expected = set(case.expected_source_ids)
    forbidden = set(case.forbidden_source_ids)
    top_k = retrieved[: case.k]
    recall = len(expected & set(top_k)) / len(expected) if expected else 1.0
    mrr = 0.0
    for rank, source_id in enumerate(top_k, start=1):
        if source_id in expected:
            mrr = 1.0 / rank
            break
    forbidden_hits = [source_id for source_id in top_k if source_id in forbidden]
    grounding = 1.0 - (len(forbidden_hits) / max(len(top_k), 1))
    metrics = {
        "recall_at_k": recall,
        "mrr": mrr,
        "grounding": grounding,
    }
    passed = not forbidden_hits
    if case.metrics:
        for metric_name, floor in case.metrics.items():
            if metrics.get(metric_name, 0.0) + 1e-9 < float(floor):
                passed = False
    costs = RunCosts(
        total=NodeCost(latency_ms=1, provider="mock", request_count=1),
    )
    notes = ""
    if forbidden_hits:
        notes = f"forbidden hits: {forbidden_hits}"
    return EvaluationResult(
        case_id=case.case_id,
        suite=case.suite,
        passed=passed,
        expected_evidence_recall=recall,
        forbidden_behavior_triggered=[f"forbidden_source:{item}" for item in forbidden_hits],
        cost_used=costs,
        notes=notes,
        metrics=metrics,
    )


def compare_with_baseline(
    results: list[EvaluationResult],
    baseline_path: Path,
    *,
    tolerance: float = 0.02,
) -> list[str]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    cases = {item["case_id"]: item for item in baseline.get("cases", [])}
    failures: list[str] = []
    for result in results:
        expected = cases.get(result.case_id)
        if expected is None:
            failures.append(f"missing baseline entry for {result.case_id}")
            continue
        for metric_name in ("recall_at_k", "mrr", "grounding"):
            actual = float(result.metrics.get(metric_name, 0.0))
            floor = float(expected.get(metric_name, 0.0)) - tolerance
            if actual + 1e-9 < floor:
                failures.append(
                    f"{result.case_id}.{metric_name} dropped below baseline "
                    f"({actual:.3f} < {floor:.3f})"
                )
        if result.forbidden_behavior_triggered:
            failures.append(
                f"{result.case_id} leaked forbidden sources: {result.forbidden_behavior_triggered}"
            )
    return failures
