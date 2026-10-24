---
title: Security
description: Trust boundaries, tenant isolation, credential handling, and prompt-injection defenses.
audience: operator
status: PROVISIONAL
scope: provisional
verifiedDate: "2026-10-21"
sourceOfTruth: engineering/SECURITY.md; engineering/architecture-v2/18-gap-register.md
---

Security is an invariant of the request path, not a feature flag. This section describes the controls that exist, the controls that fail closed, and the isolation claims that are still unproven.

::page-status{status="PROVISIONAL" verified="2026-10-21" note="Controls are implemented locally; end-to-end tenant-isolation proof remains open"}
::

## Pages

- [Overview](/docs/security/overview) — objectives, threat model, and fail-closed rules.
- [Authentication](/docs/security/authentication) — token types, pipeline, and authorization.
- [Tenant isolation](/docs/security/tenant-isolation) — RLS, Redis namespacing, ClickHouse limits.
- [Secrets and keys](/docs/security/secrets-and-keys) — Argon2id, RS256, AES-GCM, and rotation.
- [Prompt injection](/docs/security/prompt-injection) — untrusted memory, delimiters, and quarantine.

## Security invariants

| Invariant | Behavior |
| --- | --- |
| Missing tenant context | Deny; never run an unscoped query |
| Auth validation failure | 503 on protected routes; no anonymous passthrough |
| Agent/token mismatch | 403; no cross-tenant agent selection |
| Permission not held | 403; authentication is not authorization |
| Rate-limit Redis failure | 503 before provider work |
| Memory/context timeout | Degrade to directive-only context, safely |
| Secret in logs | Forbidden; use IDs and metadata |
| ClickHouse query | Must carry an explicit org predicate |

## What is not proven

::callout
---
{"type":"danger","title":"Do not claim complete isolation"}
---

  RLS and explicit `org_id` filters exist, but full-store deletion, projection fencing, backups/archives, and independent cross-tenant review are not complete. Treat “tenant isolation is fully proven” as false.

::

- Hosted HA and restore drills are not evidenced.
- The ClickHouse guard is narrower than older documentation implied: there is no global enforcement switch. Some packages reject empty org IDs or require org predicates; every query still needs an explicit filter.
- Context assembly has no caller-auth interceptor.
- Operator policy evaluation is partially wired.
- Console MFA, secure cookie deployment, CSRF, and origin controls remain readiness gates.

Never disable auth, rate limits, or RLS to recover an incident. Roll back, scale, or shed load instead.
