---
title: Auth
description: Organizations, agents, PATs, permission bitmaps, and tenant-scoped identity.
audience: integrator
status: IMPLEMENTED
scope: shipped-local
verifiedDate: "2026-10-21"
sourceOfTruth: services/auth; packages/permissions; packages/authclient
---

::page-status{status="IMPLEMENTED" verified="2026-10-21"}
::

The auth service is the identity plane. It issues and validates credentials, resolves the organization and permission bitmap, and owns provider-credential sealing. The proxy calls it over gRPC on every protected request.

::callout
---
{"type":"note","title":"HTTP surface is small"}
---

  Auth exposes HTTP `/health`, `/ready`, and `/metrics`. Token, agent, and provider-credential management is gRPC plus the management API. There is no public auth REST token API.

::

## Pages

- [Overview](/docs/auth/overview) — service responsibilities, gRPC contract, and failure modes.
- [Issuing API keys](/docs/auth/issuing-api-keys) — create, scope, and revoke PATs safely.
- [Organization and project model](/docs/auth/org-project-model) — entities and URL binding.
- [Multi-tenant RLS](/docs/auth/multi-tenant-rls) — PostgreSQL policies and verification.
- [Operator sessions](/docs/auth/operator-sessions) — PAT-to-cookie exchange, RS256, CSRF, TOTP, and step-up.

## Permission model in one table

The bitmap is defined in `packages/permissions/permissions.go`. The proxy chat requirement is `MemoryRead | SessionCreate | SessionRead | SecretUse`.

| Set | Includes | Use |
| --- | --- | --- |
| `AgentDefault` | Memory read/write, session create/read, trace read | Normal agent token |
| `ProxyChatCompletion` | Memory read, session create/read, secret use | Proxy chat admission |
| `ReadOnly` | Memory read, directive read, session read, trace read | Read-only operator |
| `Admin` | Agent default plus management bits | Organization administration |

Step-up/MFA is required for high-risk bits such as `SecretUse`, `OperatorRawRead`, and `PolicyChange`. A valid token without the required bit is authenticated but not authorized.

## Credential rules

- PATs are stored as Argon2id hashes; plaintext is returned once at creation.
- `ValidateToken` has no caller bearer and must stay on a trusted/private network boundary.
- `ValidateAgent` checks that the agent belongs to the token organization and is active.
- Provider credentials are sealed at rest and returned as metadata only.
- Revocation propagates through Redis when configured; the optional proxy auth cache is gated on a healthy revocation channel.
