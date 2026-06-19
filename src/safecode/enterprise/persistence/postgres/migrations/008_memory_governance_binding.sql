-- Bind persistent memory facts to an approved grant and mandatory expiry.

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
