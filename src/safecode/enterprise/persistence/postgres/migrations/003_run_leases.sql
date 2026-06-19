-- v2.1.5-T3 durable run lease table.

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
