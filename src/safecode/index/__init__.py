"""Code indexing.

中文包说明：代码索引子系统。
- 职责：构建 RepoMap（入口点、测试、import 关系等），支撑确定性上下文选择与评估夹具。
- 架构位置：只读分析层，输出结构化索引供 agent/context/eval 消费，不产生副作用。
- 与 Enterprise 的关系：Enterprise 检索管道可复用或扩展索引产物；索引内容视为不可信展示输入，不能绕过策略门执行变更。
"""

from safecode.index.repo_map import EntryPoint, IndexedTest, PythonImport, RepoMap, RepoMapBuilder

__all__ = ["EntryPoint", "IndexedTest", "PythonImport", "RepoMap", "RepoMapBuilder"]
