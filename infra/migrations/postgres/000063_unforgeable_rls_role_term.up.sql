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
-- The policy list below was derived from `pg_policies` on a database migrated
-- to 000062: 12 policies reference `app.is_service_account` and/or
-- `app.current_user_id` directly, and 28 policies call one of the three
-- helpers. Changing the helpers covers the 28; the 13 ALTER POLICY statements
-- below cover the 12 plus org-only `idempotency_ledger_isolation`, which must
-- gain the same service predicate as every other tenant table.

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
    SELECT current_user = 'ibex_service'
        OR (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND row_org_id = current_setting('app.current_org_id', true)::UUID
        );
$$;

CREATE OR REPLACE FUNCTION ibex_core.rls_evidence_visible(row_org_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    SELECT current_user = 'ibex_service'
        OR (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND row_org_id = current_setting('app.current_org_id', true)::UUID
        );
$$;

CREATE OR REPLACE FUNCTION ibex_core.rls_privacy_visible(row_org_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    SELECT current_user = 'ibex_service'
        OR (
            SELECT org_txt IS NOT NULL AND row_org_id = org_txt::UUID
            FROM (
                SELECT NULLIF(current_setting('app.current_org_id', true), '') AS org_txt
            ) AS guc
        );
$$;

-- Policies execute as the querying user, so every role that queries a guarded
-- table needs EXECUTE on the helper. `ibex_purge` is created by 000064; its
-- grant is added there, after the role exists.
GRANT EXECUTE ON FUNCTION ibex_core.rls_org_visible(uuid) TO ibex_app, ibex_service, ibex_evidence_relay;
GRANT EXECUTE ON FUNCTION ibex_core.rls_evidence_visible(uuid) TO ibex_app, ibex_service, ibex_evidence_relay;
GRANT EXECUTE ON FUNCTION ibex_core.rls_privacy_visible(uuid) TO ibex_app, ibex_service, ibex_evidence_relay;

-- ================================================================
-- Policies with the bypass written inline (12 at 000062)
-- ================================================================
ALTER POLICY agents_isolation ON ibex_core.agents USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
);

ALTER POLICY operator_action_ledger_isolation ON ibex_core.operator_action_ledger USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
);

ALTER POLICY org_deletion_jobs_isolation ON ibex_core.org_deletion_jobs USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
);

ALTER POLICY org_model_policies_isolation ON ibex_core.org_model_policies USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
);

ALTER POLICY org_model_policy_meta_isolation ON ibex_core.org_model_policy_meta USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
);

ALTER POLICY organization_invites_isolation ON ibex_core.organization_invites USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
);

ALTER POLICY organizations_isolation ON ibex_core.organizations USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (id = (current_setting('app.current_org_id', true))::uuid)
    )
);

ALTER POLICY provider_credentials_isolation ON ibex_core.provider_credentials USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
);

ALTER POLICY rate_limit_overrides_isolation ON ibex_core.rate_limit_overrides USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
);

ALTER POLICY tokens_isolation ON ibex_core.tokens USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
);

ALTER POLICY user_totp_secrets_isolation ON ibex_core.user_totp_secrets USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
);

-- `app.current_user_id` was never written by any service. Removing it also
-- removes the last policy reference to a dead GUC.
ALTER POLICY users_isolation ON ibex_core.users USING (
    current_user = 'ibex_service'
    OR (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
);

-- Org-only today; it must carry the same service predicate as every other
-- tenant-owned table or a SECURITY DEFINER reader cannot see it.
ALTER POLICY idempotency_ledger_isolation ON ibex_core.idempotency_ledger USING (
    current_user = 'ibex_service'
    OR (organization_id = (NULLIF(current_setting('app.current_org_id', true), ''))::uuid)
);

-- ================================================================
-- Terminate the role attribute last: every policy above already trusts
-- `current_user = 'ibex_service'`, so existing SECURITY DEFINER functions
-- owned by ibex_service keep working through the policy predicate instead of
-- an inherited role attribute.
-- ================================================================
ALTER ROLE ibex_service NOBYPASSRLS;
