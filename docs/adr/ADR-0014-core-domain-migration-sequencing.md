# ADR-0014: Core domain migration sequencing

## Status

Accepted

## Context

Phase 1 requires tenant isolation and fail-closed identity verification on the auth/proxy path. The database already contains:

- `ibex_core.organizations`
- `ibex_core.tokens` (with nullable `user_id`, `agent_id`, and `revoked_by`)

At the time of milestone 1.1.1, `users` and `agents` were intentionally deferred so the initial migration could be minimal and unblock the token/permission plane.

That deferral left two security-critical gaps identified in `docs/roadmap/phase-1-core-platform/milestones/PHASE1_GAP_ANALYSIS.md`:

- **S-2**: `tokens.user_id` / `agent_id` / `revoked_by` have no foreign keys, so revocation and tenant-scoping can’t rely on referential integrity.
- **S-1**: The proxy currently accepts `X-IBEX-Agent-ID` as a UUID without validating that the referenced agent belongs to the authenticated org. The planned fix (`M1.2.5 ValidateAgent`) depends on a real `ibex_core.agents` table.

## Decision

1. Introduce `ibex_core.users` and `ibex_core.agents` in milestone **M1.1.7** as the Phase-1 subset of the domain schema.
2. Add foreign keys for `ibex_core.tokens` in milestone **M1.1.7** using the Postgres pattern:
   - `ADD CONSTRAINT ... NOT VALID`
   - `VALIDATE CONSTRAINT` in a follow-up statement
3. Keep this milestone narrowly scoped: only the Phase-1 subset needed for `ValidateAgent` and token FK integrity. Full domain columns are deferred to later phases.

## Why `NOT VALID` + `VALIDATE CONSTRAINT`

Adding foreign keys to an existing large table can require scanning and acquiring locks. Using `NOT VALID` allows the constraint to be added without immediate validation of existing rows. Since Phase 1’s baseline data uses `NULL` values in these FK columns until the new tables exist, this keeps `make db-migrate` fast while still guaranteeing enforcement after `VALIDATE CONSTRAINT`.

## Consequences

- Referential integrity for token-scoped identities is enforced at the database layer once `M1.1.7` is applied.
- Proxy/validator logic can rely on tenant-scoped identity lookups without existence leakage.
- Migration down in development should be treated as a rollback convenience only; production rollback follows the standard migration strategy documented in `ADR-0005`.
