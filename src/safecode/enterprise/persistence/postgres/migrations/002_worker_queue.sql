-- v2.1.5-T1 worker command and queue tables.

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
