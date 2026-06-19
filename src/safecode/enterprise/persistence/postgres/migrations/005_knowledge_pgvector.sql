-- v2.4.1-T1 persistent knowledge chunks and pgvector embeddings.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS enterprise.knowledge_chunks (
    tenant_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    permission_scope JSONB NOT NULL DEFAULT '[]'::jsonb,
    freshness TEXT NOT NULL DEFAULT 'unknown',
    content_hash TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, chunk_id),
    CONSTRAINT knowledge_chunks_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0),
    CONSTRAINT knowledge_chunks_chunk_id_not_blank CHECK (length(trim(chunk_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_tenant_source
    ON enterprise.knowledge_chunks (tenant_id, source_id);

CREATE TABLE IF NOT EXISTS enterprise.knowledge_vectors (
    tenant_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    PRIMARY KEY (tenant_id, chunk_id, model_id),
    CONSTRAINT knowledge_vectors_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0),
    CONSTRAINT knowledge_vectors_chunk_id_not_blank CHECK (length(trim(chunk_id)) > 0),
    CONSTRAINT knowledge_vectors_fk_chunks
        FOREIGN KEY (tenant_id, chunk_id)
        REFERENCES enterprise.knowledge_chunks (tenant_id, chunk_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_knowledge_vectors_tenant_model
    ON enterprise.knowledge_vectors (tenant_id, model_id);
