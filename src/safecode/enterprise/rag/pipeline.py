"""Dispatch loader selection for a knowledge source.

RAG 摄取管线入口：按 KnowledgeSource.parser 分发到对应 loader。
本模块仅负责解析与加载，权限过滤在检索阶段（permission_scope / retriever）执行。
检索到的文档内容视为不可信输入，不得当作执行指令。
"""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.rag.exceptions import UnknownParserError
from safecode.enterprise.rag.loaders._common import LoaderResult
from safecode.enterprise.rag.loaders.loader_code import load_code_source
from safecode.enterprise.rag.loaders.loader_markdown import load_markdown_source
from safecode.enterprise.rag.loaders.loader_sarif import load_sarif_source
from safecode.enterprise.rag.loaders.loader_semgrep import load_semgrep_source
from safecode.enterprise.rag.source_registry import KnowledgeSource


def load_source(source: KnowledgeSource, project_root: Path) -> LoaderResult:
    """根据 source.parser 选择 loader 并加载原始记录。

    潜在问题：未知 parser 直接抛 UnknownParserError；调用方须在索引构建前校验 parser 配置。
    """
    if source.parser in {"markdown", "runbook"}:
        return load_markdown_source(source, project_root)
    if source.parser == "code":
        return load_code_source(source, project_root)
    if source.parser == "sarif":
        return load_sarif_source(source, project_root)
    if source.parser == "semgrep":
        return load_semgrep_source(source, project_root)
    raise UnknownParserError(f"unsupported parser: {source.parser}")
