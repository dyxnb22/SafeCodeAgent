-- v2.2.1-T2 webhook delivery idempotency table.

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
