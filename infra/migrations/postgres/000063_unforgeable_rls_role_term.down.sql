-- Dev/rollback only. Production migrations are forward-only (ADR-0098).
--
-- Restores the 000062 state exactly: the BYPASSRLS attribute, the three helper
-- bodies (including the forgeable `app.is_service_account` branch on
-- rls_org_visible), and the original predicates on all 13 altered policies.
-- The same ACCESS EXCLUSIVE accumulation applies; do not run this on a live
-- production database (production is forward-only).
SET LOCAL lock_timeout = '5s';

ALTER ROLE ibex_service BYPASSRLS;

-- ================================================================
-- Policies (reverse of the 13 ALTER POLICY statements in `up`)
-- ================================================================
ALTER POLICY agents_isolation ON ibex_core.agents USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL) -- NOSONAR: DDL cannot declare a constant; the legacy predicate is restored verbatim per function
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid)
    OR (current_setting('app.is_service_account', true) = 'true') -- NOSONAR: DDL cannot declare a constant; the legacy predicate is restored verbatim per function
);

ALTER POLICY operator_action_ledger_isolation ON ibex_core.operator_action_ledger USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (current_setting('app.is_service_account', true) = 'true')
);

ALTER POLICY org_deletion_jobs_isolation ON ibex_core.org_deletion_jobs USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (current_setting('app.is_service_account', true) = 'true')
);

ALTER POLICY org_model_policies_isolation ON ibex_core.org_model_policies USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (current_setting('app.is_service_account', true) = 'true')
);

ALTER POLICY org_model_policy_meta_isolation ON ibex_core.org_model_policy_meta USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (current_setting('app.is_service_account', true) = 'true')
);

ALTER POLICY organization_invites_isolation ON ibex_core.organization_invites USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (current_setting('app.is_service_account', true) = 'true')
);

ALTER POLICY organizations_isolation ON ibex_core.organizations USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (current_setting('app.is_service_account', true) = 'true')
);

ALTER POLICY provider_credentials_isolation ON ibex_core.provider_credentials USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (current_setting('app.is_service_account', true) = 'true')
);

ALTER POLICY rate_limit_overrides_isolation ON ibex_core.rate_limit_overrides USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (current_setting('app.is_service_account', true) = 'true')
);

ALTER POLICY tokens_isolation ON ibex_core.tokens USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (current_setting('app.is_service_account', true) = 'true')
);

ALTER POLICY user_totp_secrets_isolation ON ibex_core.user_totp_secrets USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (current_setting('app.is_service_account', true) = 'true')
);

ALTER POLICY users_isolation ON ibex_core.users USING (
    (
        (NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL)
        AND (org_id = (current_setting('app.current_org_id', true))::uuid)
    )
    OR (id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid)
    OR (current_setting('app.is_service_account', true) = 'true')
);

ALTER POLICY idempotency_ledger_isolation ON ibex_core.idempotency_ledger USING (
    (organization_id = (NULLIF(current_setting('app.current_org_id', true), ''))::uuid)
);

-- ================================================================
-- Helper bodies (000036/000037 originals)
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_core.rls_org_visible(row_org_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path TO 'ibex_core', 'pg_temp'
AS $$
    SELECT (
        NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
        AND row_org_id = current_setting('app.current_org_id', true)::UUID
    )
    OR current_setting('app.is_service_account', true) = 'true';
$$;

CREATE OR REPLACE FUNCTION ibex_core.rls_evidence_visible(row_org_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT (
        NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
        AND row_org_id = current_setting('app.current_org_id', true)::UUID
    );
$$;

CREATE OR REPLACE FUNCTION ibex_core.rls_privacy_visible(row_org_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT (
        SELECT org_txt IS NOT NULL AND row_org_id = org_txt::UUID
        FROM (
            SELECT NULLIF(current_setting('app.current_org_id', true), '') AS org_txt
        ) AS guc
    );
$$;

-- ================================================================
-- Grants added by `up` (ibex_app / ibex_service grants on evidence/privacy
-- helpers pre-date this migration; only the new relay and rls_org_visible
-- service grants are removed here). `ibex_purge` is dropped by 000064's down.
-- ================================================================
REVOKE EXECUTE ON FUNCTION ibex_core.rls_org_visible(uuid) FROM ibex_service, ibex_evidence_relay;
REVOKE EXECUTE ON FUNCTION ibex_core.rls_evidence_visible(uuid) FROM ibex_evidence_relay;
REVOKE EXECUTE ON FUNCTION ibex_core.rls_privacy_visible(uuid) FROM ibex_evidence_relay;
