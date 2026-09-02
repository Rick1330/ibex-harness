-- Milestone 3.5.A.2 / ADR-0062: durable dead-letter store for exhausted-retry Celery tasks.
-- No RLS (operator forensics; service-account inserts — see ADR-0062).

CREATE TABLE ibex_core.failed_tasks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_name           TEXT NOT NULL,
    task_id             TEXT NOT NULL,
    args                JSONB NOT NULL DEFAULT '[]',
    kwargs              JSONB NOT NULL DEFAULT '{}',
    exception_type      TEXT NOT NULL,
    exception_message   TEXT NOT NULL,
    traceback           TEXT NOT NULL,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    failed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    org_id              UUID REFERENCES ibex_core.organizations(id) ON DELETE SET NULL
);

CREATE INDEX idx_failed_tasks_failed_at
    ON ibex_core.failed_tasks (failed_at DESC);

CREATE INDEX idx_failed_tasks_org_failed_at
    ON ibex_core.failed_tasks (org_id, failed_at DESC)
    WHERE org_id IS NOT NULL;

CREATE UNIQUE INDEX idx_failed_tasks_task_id
    ON ibex_core.failed_tasks (task_id);

-- INSERT-only for ibex_app; operator forensics use migration/superuser role (ADR-0062).
GRANT INSERT ON ibex_core.failed_tasks TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;
