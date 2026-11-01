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

## Consequences

- Operators cannot mistake `CONSOLE_READ_ONLY` for a security control.
- Tests and reviews can assert the boundary by checking the route surface rather than an environment variable.
- A future mutation surface has a clear, higher bar: a new ADR and a full write contract.

## Rollback

Revert this record and restore the documentation claim. No code, data, or configuration changes are involved.
