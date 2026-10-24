---
title: Architecture Decision Records
description: Decision records for IBEX Harness — auth, proxy, memory, context, evidence, and operations.
audience: contributor
---

# Architecture Decision Records

Each ADR captures a decision, its context, consequences, and its own status. Browse the records in this directory through ADR-0087.

Decision records are not implementation evidence. A record can be **Proposed**, **Accepted**, **Rejected**, or **Superseded** while the runtime remains provisional or absent. The authoritative runtime claim is the [status ledger](../architecture-v2/00-status-and-evidence.md).

Notable records:

- [ADR-0087](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0087-public-site-nuxt-docus-migration.md) — public site migration to Nuxt 4 + Docus.
- [ADR-0086](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0086-mcp-operator-gateway.md) — read-only MCP operator gateway, local and default-off.
- [ADR-0085](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0085-evidence-relay-daemon-and-session-fence.md) — evidence relay daemon and session fence.
- [ADR-0084](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0084-g0-principal-agent-binding-and-idempotency.md) — G0 principal, agent binding, and idempotency contract.
- [ADR-0071](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0071-context-grpc-degradation-deadline.md) — context deadlines and degradation.
- [ADR-0060](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0060-memory-service-tenant-isolation.md) — memory tenant isolation.

Numbers are not contiguous; ADR-0036 and ADR-0037 are not published.

## Conventions

- ADRs live in `engineering/adr/`.
- Keep the decision, alternatives, and consequences explicit.
- Do not rewrite an accepted decision silently. Supersede it with a new record.
- Link runtime evidence to the status ledger, not to the ADR alone.
