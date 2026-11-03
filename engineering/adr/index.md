---
title: Architecture Decision Records
description: Decision records for IBEX Harness — auth, proxy, memory, context, evidence, and operations.
audience: contributor
---

# Architecture Decision Records

Each ADR captures a decision, its context, consequences, and its own status. Browse the records in this directory through ADR-0089.

Decision records are not implementation evidence. A record can be **Proposed**, **Accepted**, **Rejected**, or **Superseded** while the runtime remains provisional or absent. The authoritative runtime claim is the [status ledger](../architecture-v2/00-status-and-evidence.md).

Notable records:

- [ADR-0095](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0095-retrieval-and-agreement-metrics.md) — nDCG@k, tail-extrapolated RBO, and Cohen's kappa defined once in `services/memory/app/eval`, shared by the
  benchmark and the shadow path.
- [ADR-0094](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0094-bounded-lineage-and-conflict-suppression.md) — depth-capped lineage traversal in SQL, and unresolved-conflict suppression keyed on pending escalations across search, hot cache, and context assembly.
- [ADR-0093](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0093-cross-encoder-rerank-as-relevance.md) — cross-encoder rerank replaces the relevance component, default off, degrades to the fused order.
- [ADR-0092](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0092-hybrid-retrieval-rrf-admission.md) — hybrid retrieval: RRF decides admission, composite scoring decides presentation, default off.
- [ADR-0089](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0089-product-shape-and-console-scope.md) — memory/context product shape, Console core/platform tiers, preview policy, and packaging.
- [ADR-0088](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0088-console-nuxt-shadcn-vue-migration.md) — Console migration to Nuxt 4 + shadcn-vue with a same-origin BFF.
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
