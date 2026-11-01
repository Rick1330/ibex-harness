---
title: "ADR-0091: Console read-only is structural"
description: "Architecture decision record 0091: the Console has no mutation routes and does not consult CONSOLE_READ_ONLY; any future write path needs its own contract, CSRF, audit, idempotency, and tenant checks."
adrId: "0091"
status: "Accepted"
date: "2026-11-01"
authors: "Elshaday Mengesha (@Rick1330)"
---

::decision-banner{status="Accepted" date="2026-11-01" id="0091"}
::

# ADR-0091: Console read-only is structural

- **Status:** Accepted
- **Date:** 2026-11-01
- **Author:** Elshaday Mengesha (@Rick1330)
- **Amends:** the read-only requirement for the Console in [ADR-0088](0088-console-nuxt-shadcn-vue-migration.md). The ADR-0088 body is unchanged.
- **Related:** [ADR-0089](0089-product-shape-and-console-scope.md), [ADR-0090](0090-retire-dashboard-compatibility-shell.md).

## Context

The Console is a read-only operator application. It exposes no create, update, delete, pause, archive, or replay routes.
Read-only behavior comes from that route surface, not from a runtime switch.

`CONSOLE_READ_ONLY` predates the Nuxt implementation. The current Console does not read it. Documentation that says the
variable "keeps the console read-only" implies a runtime guarantee that does not exist, and an operator could rely on a
setting that has no effect.

## Decision

1. Read-only is structural: the Console ships no mutation routes. `CONSOLE_READ_ONLY` is reserved and ignored.
2. Deployment configuration may omit the variable. Setting it does not enable, disable, or restrict anything.
3. Any future write path requires a new ADR and an owning contract, plus authentication, permission and step-up checks,
   CSRF protection, audit events, idempotency, tenant-negative tests, and a rollback story. It must not be enabled by
   flipping a flag.
4. Documentation describes the structural boundary and marks the variable reserved and ignored.

## What this record does and does not claim

- It does **not** claim that login, session issuance, or any write path is accepted.
- It does **not** weaken the read-only boundary; it removes a misleading configuration claim.
- It does **not** change the Console route surface, contracts, or environment parsing.

## Options considered

1. **Keep the flag and consult it.** Rejected: the Console has no mutation routes, so a runtime flag would imply a
   control that does not exist and could drift from the route surface.
2. **Remove the variable everywhere.** Rejected: deployment templates and historical configs still set it; ignoring it
   with a clear label is less disruptive.
3. **Make read-only structural and document the variable as reserved.** Adopted: the route surface is the control, and
   a future write path must add its own contract and safety checks.

## Rollout / migration plan

No runtime change. Operators may leave `CONSOLE_READ_ONLY` unset or keep it; it has no effect. Documentation marks it
reserved and ignored. A future mutation surface must land with a new ADR, an owning API contract, CSRF, audit,
idempotency, tenant-negative tests, and a rollback plan before it is enabled.

## Consequences

- Operators cannot mistake `CONSOLE_READ_ONLY` for a security control.
- Tests and reviews can assert the boundary by checking the route surface rather than an environment variable.
- A future mutation surface has a clear, higher bar: a new ADR and a full write contract.

## Rollback

Revert this record and restore the documentation claim. No code, data, or configuration changes are involved.

## References

- [ADR-0088](0088-console-nuxt-shadcn-vue-migration.md) — the read-only requirement this record amends.
- [ADR-0089](0089-product-shape-and-console-scope.md) — the Console surface scope.
- `services/console/README.md` — the structural read-only statement.
- `engineering/ENVIRONMENT_VARIABLES.md` — the reserved-variable entry.
