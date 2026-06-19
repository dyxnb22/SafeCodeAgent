-- v2.5.2 worker dead-letter queue support.

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
