-- Dev/rollback only. Production migrations are forward-only (ADR-0098).
--
-- Reverses 000068: restores the token reader to ibex_runtime while
-- `auth_find_token_by_prefix` still exists (it is dropped later by 000065's
-- down, not here), removes the membership and every privilege granted to
-- ibex_auth, then drops the role.

-- Restore the 000065 grant before the login that uses it is removed.
GRANT EXECUTE ON FUNCTION ibex_core.auth_find_token_by_prefix(text) TO ibex_runtime;
REVOKE EXECUTE ON FUNCTION ibex_core.auth_find_token_by_prefix(text) FROM ibex_auth;

-- DROP OWNED does not remove role memberships, so revoke it explicitly.
REVOKE ibex_app FROM ibex_auth;

DROP OWNED BY ibex_auth;
DROP ROLE IF EXISTS ibex_auth;
