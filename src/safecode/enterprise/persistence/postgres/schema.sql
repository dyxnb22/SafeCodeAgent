-- Enterprise persistence schema (v2.1.3-T1).
-- Canonical DDL snapshot; migrations must stay in sync.

CREATE SCHEMA IF NOT EXISTS enterprise;

CREATE TABLE IF NOT EXISTS enterprise.schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS enterprise.checkpoints (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    completed_nodes JSONB NOT NULL DEFAULT '[]'::jsonb,
    next_node TEXT,
    state JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, run_id),
    CONSTRAINT checkpoints_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_tenant_updated
    ON enterprise.checkpoints (tenant_id, updated_at);

CREATE TABLE IF NOT EXISTS enterprise.approval_requests (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, run_id, request_id),
    CONSTRAINT approval_requests_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_tenant_run_status
    ON enterprise.approval_requests (tenant_id, run_id, status);

CREATE TABLE IF NOT EXISTS enterprise.grants (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    grant_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    consumed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, run_id, grant_id),
    CONSTRAINT grants_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0)
);

CREATE TABLE IF NOT EXISTS enterprise.audit_events (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    run_id TEXT,
    actor_id TEXT NOT NULL,
    event JSONB NOT NULL,
    previous_hash TEXT,
    event_hash TEXT NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    CONSTRAINT audit_events_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_run
    ON enterprise.audit_events (tenant_id, run_id, id);

CREATE TABLE IF NOT EXISTS enterprise.eval_results (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    results JSONB NOT NULL,
    written_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, run_id),
    CONSTRAINT eval_results_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0)
);

CREATE TABLE IF NOT EXISTS enterprise.evidence_index (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    bundle_path TEXT NOT NULL,
    exported_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, run_id),
    CONSTRAINT evidence_index_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0)
);

CREATE TABLE IF NOT EXISTS enterprise.trace_events (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (tenant_id, run_id, event_id),
    UNIQUE (tenant_id, run_id, seq),
    CONSTRAINT trace_events_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0)
);

CREATE TABLE IF NOT EXISTS enterprise.run_commands (
    tenant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    command TEXT NOT NULL,
    run_id TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key),
    CONSTRAINT run_commands_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0),
    CONSTRAINT run_commands_idempotency_key_not_blank CHECK (length(trim(idempotency_key)) > 0)
);

CREATE TABLE IF NOT EXISTS enterprise.queue (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT queue_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_queue_pending_created
    ON enterprise.queue (created_at, job_id)
    WHERE status IN ('pending', 'leased');

CREATE TABLE IF NOT EXISTS enterprise.run_leases (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, run_id),
    CONSTRAINT run_leases_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_run_leases_expires
    ON enterprise.run_leases (expires_at);

CREATE TABLE IF NOT EXISTS enterprise.webhook_events (
    delivery_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    run_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT webhook_events_delivery_id_not_blank CHECK (length(trim(delivery_id)) > 0),
    CONSTRAINT webhook_events_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_tenant_created
    ON enterprise.webhook_events (tenant_id, created_at DESC);

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

CREATE TABLE IF NOT EXISTS enterprise.memory_facts (
    tenant_id TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    content TEXT NOT NULL,
    provenance TEXT NOT NULL,
    approver TEXT NOT NULL,
    admitted_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    permission_scope JSONB NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (tenant_id, fact_id),
    CONSTRAINT memory_facts_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0),
    CONSTRAINT memory_facts_fact_id_not_blank CHECK (length(trim(fact_id)) > 0),
    CONSTRAINT memory_facts_status_valid CHECK (status IN ('active', 'revoked', 'expired'))
);

CREATE INDEX IF NOT EXISTS idx_memory_facts_tenant_status
    ON enterprise.memory_facts (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_memory_facts_tenant_expires
    ON enterprise.memory_facts (tenant_id, expires_at)
    WHERE expires_at IS NOT NULL;

ALTER TABLE enterprise.queue
    ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS enterprise.dlq (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    command TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempts INT NOT NULL DEFAULT 0,
    poison BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    dlq_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT dlq_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_dlq_tenant_created
    ON enterprise.dlq (tenant_id, dlq_at DESC);

ALTER TABLE enterprise.memory_facts
    ADD COLUMN IF NOT EXISTS approval_request_id TEXT,
    ADD COLUMN IF NOT EXISTS approval_grant_id TEXT,
    ADD COLUMN IF NOT EXISTS policy_snapshot_id TEXT;

UPDATE enterprise.memory_facts
SET approval_request_id = COALESCE(approval_request_id, 'legacy-unverified'),
    approval_grant_id = COALESCE(approval_grant_id, 'legacy-unverified'),
    policy_snapshot_id = COALESCE(policy_snapshot_id, 'legacy-unverified'),
    status = CASE WHEN expires_at IS NULL THEN 'revoked' ELSE status END,
    expires_at = COALESCE(expires_at, admitted_at);

ALTER TABLE enterprise.memory_facts
    ALTER COLUMN approval_request_id SET NOT NULL,
    ALTER COLUMN approval_grant_id SET NOT NULL,
    ALTER COLUMN policy_snapshot_id SET NOT NULL,
    ALTER COLUMN expires_at SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_memory_facts_tenant_grant
    ON enterprise.memory_facts (tenant_id, approval_grant_id);

ALTER TABLE enterprise.run_leases
    ADD COLUMN IF NOT EXISTS fence_token TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS enterprise.api_idempotency (
    tenant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    response JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, idempotency_key),
    CONSTRAINT api_idempotency_tenant_id_not_blank CHECK (length(trim(tenant_id)) > 0),
    CONSTRAINT api_idempotency_key_not_blank CHECK (length(trim(idempotency_key)) > 0)
);
