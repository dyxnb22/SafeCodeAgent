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
