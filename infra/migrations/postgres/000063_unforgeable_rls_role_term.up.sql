-- P0-06 foundation: terminate the forgeable RLS bypass.
--
-- Before this migration every tenant policy trusts `app.is_service_account`
-- (or the never-written `app.current_user_id`). Any role that can run SQL can
-- set a custom GUC, so the bypass is forgeable by the tenant role itself.
--
-- The replacement predicate is `current_user = 'ibex_service'`, which a tenant
-- role cannot forge: `current_user` is set by the server, and only a role that
-- is a member of `ibex_service` (or a SECURITY DEFINER function owned by it)
-- can run with that identity.
--
-- The three helper functions stay SECURITY INVOKER on purpose. Inside a
-- SECURITY DEFINER function `current_user` is the owner, so a definer helper
-- would make every policy pass for every caller.
--
-- One source of truth: every tenant policy calls one of these helpers with its
-- org column. The CASE guarantees PostgreSQL evaluates only the selected arm,
-- so a pooled connection that left `app.current_org_id = ''` behind cannot make
-- the `::uuid` cast run in the service branch. `COALESCE(..., false)` makes the
-- empty or unset GUC fail closed instead of raising 22P02.
--
-- The policy list below was derived from `pg_policies` on a database migrated
-- to 000062: 12 policies referenced the GUCs directly and 28 called one of the
-- three helpers. After this migration all 41 call a helper.

-- Every ALTER POLICY takes ACCESS EXCLUSIVE on its table (measured via
-- pg_locks), and this file is one transaction, so the locks accumulate until
-- COMMIT. Fail fast and retry rather than queue a long-lived reader behind the
-- migration; run it in a low-traffic window.
SET LOCAL lock_timeout = '5s';

-- ================================================================
-- Helper functions (SECURITY INVOKER)
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_core.rls_org_visible(row_org_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path TO 'ibex_core', 'pg_temp'
AS $$
    SELECT CASE
        WHEN current_user = 'ibex_service' THEN true
        ELSE COALESCE(
            NULLIF(current_setting('app.current_org_id', true), '')::uuid = row_org_id,
            false
        )
    END;
$$;

CREATE OR REPLACE FUNCTION ibex_core.rls_evidence_visible(row_org_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    SELECT ibex_core.rls_org_visible(row_org_id);
$$;

CREATE OR REPLACE FUNCTION ibex_core.rls_privacy_visible(row_org_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    SELECT ibex_core.rls_org_visible(row_org_id);
$$;

-- Policies execute as the querying user, so every role that queries a guarded
-- table needs EXECUTE on the helper. `ibex_purge` is created by 000064; its
-- grant is added there, after the role exists.
GRANT EXECUTE ON FUNCTION ibex_core.rls_org_visible(uuid) TO ibex_app, ibex_service, ibex_evidence_relay;
GRANT EXECUTE ON FUNCTION ibex_core.rls_evidence_visible(uuid) TO ibex_app, ibex_service, ibex_evidence_relay;
GRANT EXECUTE ON FUNCTION ibex_core.rls_privacy_visible(uuid) TO ibex_app, ibex_service, ibex_evidence_relay;

-- ================================================================
-- Every tenant policy now calls the helper (13 altered in place; the other 28
-- already did). No inline `current_user` / GUC predicates remain.
-- ================================================================
ALTER POLICY agents_isolation ON ibex_core.agents
    USING (ibex_core.rls_org_visible(org_id));

ALTER POLICY operator_action_ledger_isolation ON ibex_core.operator_action_ledger
    USING (ibex_core.rls_org_visible(org_id));

ALTER POLICY org_deletion_jobs_isolation ON ibex_core.org_deletion_jobs
    USING (ibex_core.rls_org_visible(org_id));

ALTER POLICY org_model_policies_isolation ON ibex_core.org_model_policies
    USING (ibex_core.rls_org_visible(org_id));

ALTER POLICY org_model_policy_meta_isolation ON ibex_core.org_model_policy_meta
    USING (ibex_core.rls_org_visible(org_id));

ALTER POLICY organization_invites_isolation ON ibex_core.organization_invites
    USING (ibex_core.rls_org_visible(org_id));

ALTER POLICY organizations_isolation ON ibex_core.organizations
    USING (ibex_core.rls_org_visible(id));

ALTER POLICY provider_credentials_isolation ON ibex_core.provider_credentials
    USING (ibex_core.rls_org_visible(org_id));

ALTER POLICY rate_limit_overrides_isolation ON ibex_core.rate_limit_overrides
    USING (ibex_core.rls_org_visible(org_id));

ALTER POLICY tokens_isolation ON ibex_core.tokens
    USING (ibex_core.rls_org_visible(org_id));

ALTER POLICY user_totp_secrets_isolation ON ibex_core.user_totp_secrets
    USING (ibex_core.rls_org_visible(org_id));

ALTER POLICY users_isolation ON ibex_core.users
    USING (ibex_core.rls_org_visible(org_id));

ALTER POLICY idempotency_ledger_isolation ON ibex_core.idempotency_ledger
    USING (ibex_core.rls_org_visible(organization_id));

-- ================================================================
-- Terminate the role attribute last: every policy above already trusts
-- `current_user = 'ibex_service'`, so existing SECURITY DEFINER functions
-- owned by ibex_service keep working through the policy predicate instead of
-- an inherited role attribute.
-- ================================================================
ALTER ROLE ibex_service NOBYPASSRLS;
