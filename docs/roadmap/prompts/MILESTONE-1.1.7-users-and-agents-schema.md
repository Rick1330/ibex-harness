## What and Why

Reconcile DATABASE_SCHEMA with reality by introducing `ibex_core.users` and `ibex_core.agents` plus the deferred foreign key constraints on `ibex_core.tokens`. Close security gaps addressed by [M1.2.5](../phase-1-core-platform/milestones/1.2.5-proxy-agent-identity-verification.md) (agent identity) and token FK integrity so that agent-scoped tokens and proxy `X-IBEX-Agent-ID` lookups can rely on enforced org ownership.

## How

- Add migrations `000005_create_set_updated_at_function`, `000006_create_users`, `000007_create_agents`, `000008_tokens_fk_constraints` under `infra/migrations/postgres/` following ADR-0005.
- Implement `ibex_core.users` and `ibex_core.agents` as the Phase-1 column subset with RLS enabled and `set_updated_at()` triggers wired.
- Add `NOT VALID` foreign keys from `tokens.user_id`, `tokens.agent_id`, and `tokens.revoked_by` to `users`/`agents`, then `VALIDATE CONSTRAINT` to keep `db-migrate` fast and idempotent.
- Extend the auth service with a `ValidateAgent` gRPC RPC backed by an agents repository using the existing `database/sql` + `lib/pq` pattern.
- Ensure `ValidateAgent` returns `PERMISSION_DENIED` (not `NOT_FOUND`) for cross-org or inactive agents, per the security rules in the milestone.

## Testing

- `make db-migrate` and `make db-version` show the new highest migration version; a second `make db-migrate` is a no-op.
- Integration tests in `infra/migrations/postgres` and `infra/testing/testutil` cover:
  - `ibex_core.users` and `ibex_core.agents` existence and RLS behavior.
  - FK enforcement on `tokens.user_id`, `tokens.agent_id`, and `tokens.revoked_by`.
- New auth integration tests verify:
  - `ValidateAgent` returns success for an active agent in the caller org.
  - `ValidateAgent` returns `PERMISSION_DENIED` for cross-org and inactive agents.

## Security

- Enforced foreign keys prevent dangling `user_id`/`agent_id`/`revoked_by` references in `ibex_core.tokens`.
- RLS on `users` and `agents` continues the `app.current_org_id` / `app.is_service_account` pattern so that service accounts can manage identity while normal app roles remain tenant-scoped.
- `ValidateAgent` avoids leaking the existence of agents in other orgs by failing with `PERMISSION_DENIED` instead of `NOT_FOUND` on cross-tenant lookups.

## Docs

- New ADR-0014 describing core domain migration sequencing and the `NOT VALID` FK pattern.
- `docs/DATABASE_SCHEMA.md` updated to mark `users` and `agents` as applied via M1.1.7 and to call out deferred columns as Phase 3+.
- Phase-1 roadmap `README.md`, `goals.md`, `decisions.md`, and `CURRENT_STATE.md` updated to include M1.1.7 and execution order for downstream milestones (1.2.5, 1.5.1).
