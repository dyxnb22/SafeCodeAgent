-- R8: lease fencing token and API idempotency records.

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
