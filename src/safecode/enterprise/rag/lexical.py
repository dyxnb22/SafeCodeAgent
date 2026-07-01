"""Lexical BM25-ish scorer for enterprise RAG.

中文模块说明：RAG 词法打分支路，确定性 BM25 风格评分，无外部模型依赖。
- 架构位置：``retriever.py`` 混合检索的第一路；v1.1 起默认足够（决策 D15）。
- 安全不变量：纯本地计算，适合离线 demo 与面试复现。
- 学习路径：读 ``retriever.py`` 的分数融合逻辑。
"""

from __future__ import annotations

import math
import re
from collections import Counter

from safecode.enterprise.rag.models import Chunk

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "with",
    }
)


def tokenize(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    return [token for token in tokens if token not in _STOPWORDS and len(token) > 1]


def score_chunks(query: str, chunks: list[Chunk]) -> dict[str, float]:
    """Return deterministic lexical scores keyed by chunk_id."""
    query_terms = tokenize(query)
    if not query_terms or not chunks:
        return {chunk.chunk_id: 0.0 for chunk in chunks}

    doc_tokens = {chunk.chunk_id: tokenize(chunk.text) for chunk in chunks}
    doc_freq: Counter[str] = Counter()
    for tokens in doc_tokens.values():
        doc_freq.update(set(tokens))

    num_docs = len(chunks)
    scores: dict[str, float] = {}
    query_counts = Counter(query_terms)
    avg_doc_len = sum(len(tokens) for tokens in doc_tokens.values()) / max(num_docs, 1)
    k1 = 1.2
    b = 0.75

    for chunk in chunks:
        tokens = doc_tokens[chunk.chunk_id]
        if not tokens:
            scores[chunk.chunk_id] = 0.0
            continue
        term_freq = Counter(tokens)
        doc_len = len(tokens)
        total = 0.0
        for term, qf in query_counts.items():
            df = doc_freq.get(term, 0)
            idf = math.log(1 + (num_docs - df + 0.5) / (df + 0.5))
            tf = term_freq.get(term, 0)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * (doc_len / max(avg_doc_len, 1)))
            total += idf * (numerator / max(denominator, 1e-9)) * qf
        scores[chunk.chunk_id] = total

    max_score = max(scores.values()) if scores else 1.0
    if max_score <= 0:
        return scores
    return {chunk_id: value / max_score for chunk_id, value in scores.items()}
