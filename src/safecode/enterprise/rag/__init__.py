"""Enterprise RAG ingestion, chunking, and retrieval.

中文包说明：企业检索增强生成（RAG）子系统。
- 检索内容视为不可信输入，须保留来源标识、引用与权限裁决；不得将文档内容当作执行指令。
- 每个 Chunk 携带 permission_scope 与 tenant_id，检索阶段须按主体权限过滤。
- 分块前对文本做秘密脱敏；索引与查询均受租户边界约束。
"""
