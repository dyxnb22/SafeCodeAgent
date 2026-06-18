"""Enterprise retrieval evaluation runner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from safecode.enterprise.rag.index_builder import build_chunks_from_manifest
from safecode.enterprise.rag.retriever import HybridRetriever, RetrievalFilters
from safecode.enterprise.rag.source_registry import SourceType


@dataclass(frozen=True)
class RetrievalEvalCase:
    case_id: str
    query: str
    actor_scope: list[str]
    actor_tenant: str
    expected_source_ids: list[str]
    forbidden_source_ids: list[str]
    k: int
    metrics: dict[str, float]


@dataclass(frozen=True)
class RetrievalEvalResult:
    case_id: str
    recall_at_k: float
    mrr: float
    grounding: float
    retrieved_source_ids: list[str]
    forbidden_hits: list[str]


def load_eval_case(path: Path) -> RetrievalEvalCase:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"invalid eval case: {path}")
    filters = raw.get("filters") or {}
    source_types = filters.get("source_types")
    _ = source_types
    metrics = raw.get("metrics") or {}
    return RetrievalEvalCase(
        case_id=str(raw["case_id"]),
        query=str(raw["query"]),
        actor_scope=[str(item) for item in raw.get("actor_scope", [])],
        actor_tenant=str(raw.get("actor_tenant", "local")),
        expected_source_ids=[str(item) for item in raw.get("expected_source_ids", [])],
        forbidden_source_ids=[str(item) for item in raw.get("forbidden_source_ids", [])],
        k=int(raw.get("k", 5)),
        metrics={str(key): float(value) for key, value in metrics.items()},
    )


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


def run_case(
    case_path: Path,
    manifest_path: Path,
    project_root: Path,
) -> RetrievalEvalResult:
    raw = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    case = load_eval_case(case_path)
    chunks = build_chunks_from_manifest(manifest_path, project_root)
    retriever = HybridRetriever(chunks=chunks)
    filters = _build_filters(raw.get("filters") if isinstance(raw, dict) else None)
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
    return RetrievalEvalResult(
        case_id=case.case_id,
        recall_at_k=recall,
        mrr=mrr,
        grounding=grounding,
        retrieved_source_ids=retrieved,
        forbidden_hits=forbidden_hits,
    )


def run_suite(
    case_paths: list[Path],
    manifest_path: Path,
    project_root: Path,
) -> list[RetrievalEvalResult]:
    return [run_case(path, manifest_path, project_root) for path in case_paths]


def compare_with_baseline(
    results: list[RetrievalEvalResult],
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
        for metric_name, actual in {
            "recall_at_k": result.recall_at_k,
            "mrr": result.mrr,
            "grounding": result.grounding,
        }.items():
            floor = float(expected.get(metric_name, 0.0)) - tolerance
            if actual + 1e-9 < floor:
                failures.append(
                    f"{result.case_id}.{metric_name} dropped below baseline "
                    f"({actual:.3f} < {floor:.3f})"
                )
        if result.forbidden_hits:
            failures.append(f"{result.case_id} leaked forbidden sources: {result.forbidden_hits}")
    return failures
