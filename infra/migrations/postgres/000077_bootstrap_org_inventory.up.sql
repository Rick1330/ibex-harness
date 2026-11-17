-- P2-13: the bootstrap command can see which organizations already exist.
--
-- `services/auth/internal/bootstrap` creates the first organization, its owner,
-- and an admin PAT, and is idempotent per slug: a rerun naming the same slug
-- reconciles the memory service token and creates nothing. A rerun naming a
-- *different* slug on a deployed installation was not guarded at all, so the
-- one-shot minted a second owner credential and a second tenant on an install
-- that already had one. Nothing in the command could see that, because
-- `ibex_bootstrap` holds no table privilege (000069:7-14) and its definers each
-- take an organization id the caller supplied.
--
-- This adds the one read the guard needs: the slugs of the installation's
-- non-deleted organizations. It returns slugs, not ids, because that is the
-- only value the decision needs and the caller already supplies its own slug;
-- user, agent and credential rows stay out of reach.
--
-- The body is a plain cross-tenant read, and that is deliberate. It runs as
-- `ibex_service`, which the tenant policy admits (000063), so it sees every
-- organization. The capability is bounded by what the value is: a slug is the
-- name an operator typed into IBEX_BOOTSTRAP_ORG_SLUG, it is not secret, and the
-- one-shot already learns the same slug from its own environment. Reading it
-- cannot write into another tenant, which is the boundary 000069 sets. The
-- SECURITY DEFINER grant stays where every other bootstrap definer's is: to
-- `ibex_bootstrap` only, REVOKEd from PUBLIC.
--
-- `SELECT (slug)` on ibex_core.organizations is already granted to
-- `ibex_service` by 000069, and RLS admits the owner there, so no new table
-- privilege is needed.
--
-- Consumers: `guardSecondOrganization` in services/auth/internal/bootstrap/
-- bootstrap.go refuses a slug that is not among these when the installation
-- already has one, unless IBEX_BOOTSTRAP_ALLOW_SECOND_ORG=true says the second
-- owner credential is intended. A soft-deleted organization is excluded: it
-- cannot be reconciled, and `bootstrap_upsert_organization` already names it
-- when the requested slug belongs to one.

SET LOCAL lock_timeout = '5s';

CREATE OR REPLACE FUNCTION ibex_core.bootstrap_list_org_slugs()
RETURNS TABLE (slug text)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
    SELECT o.slug
    FROM ibex_core.organizations o
    WHERE o.deleted_at IS NULL
    -- Ordered by slug, the one column 000069 grants to `ibex_service`, so the
    -- body needs no further column privilege. The order is only there to make
    -- the refusal text stable across runs.
    ORDER BY o.slug;
$$;

ALTER FUNCTION ibex_core.bootstrap_list_org_slugs() OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.bootstrap_list_org_slugs() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ibex_core.bootstrap_list_org_slugs() TO ibex_bootstrap;
