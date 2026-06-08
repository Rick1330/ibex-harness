-- infra/scripts/seed_dev.sql
-- Idempotent development seed data.
-- Safe to run multiple times: all inserts use ON CONFLICT DO NOTHING.
--
-- SECURITY: Never run against staging or production databases.
-- Run via: make db-seed
--
-- Dev seed PAT (ADR-0007 wire form, fixed token row UUID):
--   ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY
-- Hash generated with: go run ./infra/tools/hashtoken <bearer>

BEGIN;

SELECT set_config('app.is_service_account', 'true', true);

INSERT INTO ibex_core.organizations (id, name, slug, tier, status)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'IBEX Dev Org',
    'ibex-dev',
    'free',
    'active'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO ibex_core.users (id, org_id, email, name, role, status)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'dev@ibex.local',
    'Dev User',
    'owner',
    'active'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
VALUES (
    '00000000-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000002',
    'Dev Agent',
    'dev-agent',
    'active'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO ibex_core.tokens (
    id, org_id, user_id, agent_id,
    type, hash, prefix, name,
    permissions, is_revoked
) VALUES (
    '00000000-0000-0000-0000-000000000004',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000003',
    'pat',
    '$argon2id$v=19$m=65536,t=3,p=4$v7OU5izBPGnx4P47/nOoGQ$Ozd/9sqIqvtVBwk5fdfTGnXGkmflQej0xtooVgaAxh8',
    'ibex_pat_00000000-0000-0000-0000-000000000004',
    'Dev Seed Token',
    270633733891,
    false
) ON CONFLICT (id) DO NOTHING;

COMMIT;
