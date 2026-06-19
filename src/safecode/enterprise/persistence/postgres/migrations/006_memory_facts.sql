-- v2.4.6-T1 governed long-term memory facts.

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
