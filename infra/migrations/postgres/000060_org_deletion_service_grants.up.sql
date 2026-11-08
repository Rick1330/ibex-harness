-- W3 tenancy and erasure: the organization-deletion purge is a cross-tenant
-- admin operation and belongs to `ibex_service` (BYPASSRLS, NOLOGIN, never
-- granted to ibex_app), not to the tenant role. These are the first grants for
-- that move; the remaining purge tables still need their own grants before the
-- worker can actually run the stage as ibex_service.
--
-- `legal_holds` already carries SELECT/INSERT/UPDATE/DELETE for ibex_service
-- from 000037, so it is deliberately not repeated here.
GRANT DELETE ON ibex_core.session_events TO ibex_service;
GRANT DELETE ON ibex_core.directive_versions TO ibex_service;
