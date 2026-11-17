-- The read exists only for the second-organization guard in
-- services/auth/internal/bootstrap; dropping it restores the pre-guard state
-- where the command could not see any other tenant.
DROP FUNCTION IF EXISTS ibex_core.bootstrap_list_org_slugs();
