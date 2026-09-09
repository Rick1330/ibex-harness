-- Thin async job status for org GDPR deletion (not a generic job platform).
CREATE TABLE ibex_core.org_deletion_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);

CREATE INDEX idx_org_deletion_jobs_org_id
    ON ibex_core.org_deletion_jobs(org_id, created_at DESC);

ALTER TABLE ibex_core.org_deletion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.org_deletion_jobs FORCE ROW LEVEL SECURITY;

CREATE POLICY org_deletion_jobs_isolation ON ibex_core.org_deletion_jobs
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.org_deletion_jobs TO ibex_app;

CREATE TRIGGER org_deletion_jobs_updated_at
    BEFORE UPDATE ON ibex_core.org_deletion_jobs
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
