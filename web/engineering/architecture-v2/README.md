# IBEX Harness Architecture v2

**Status:** Documentation baseline / proposed target architecture
**Owner:** Platform architecture
**Last reviewed:** 2026-10-03

## Purpose

This directory is the canonical architecture baseline for the next implementation cycle. It replaces the earlier single-topology narrative with explicit planes, authorities, contracts, trust boundaries, and evidence gates.

It is intentionally **not** a claim that every described component is already implemented or production-ready.

## Status vocabulary

| Class | Meaning |
|---|---|
| `shipped-accepted` | Implemented, tested, and accepted for a named deployment profile with linked evidence. |
| `shipped-local` | Works in the repository/local profile, but hosted or production acceptance is not complete. |
| `provisional` | Mounted or partially implemented; behavior, security, or operations remain gated. |
| `specified` | Contract/design is accepted but implementation is not complete. |
| `design-intent` | Proposed direction; not an implementation contract yet. |
| `target` | Desired measurable property, not a result. |
| `deferred` | Explicitly outside the current implementation sequence. |
| `unknown` | Not established by source, test, benchmark, or deployment evidence. |

Every claim in canonical docs must use one of these classes. A directory, route, diagram, README, or passing unit test alone is not production evidence.

## Canonical precedence

1. Accepted ADRs and versioned contracts.
2. This architecture-v2 directory.
3. Security and release gates.
4. Service/package READMEs and implementation documentation.
5. Public roadmap and current-state pages.
6. Historical reports and exploratory research.

If documents disagree, implementation must stop at the boundary, the conflict must be recorded in [`18-gap-register.md`](18-gap-register.md), and an ADR or contract update must resolve it.

## Reading order

1. [00-status-and-evidence.md](00-status-and-evidence.md)
2. [01-target-topology.md](01-target-topology.md)
3. [02-plane-boundaries.md](02-plane-boundaries.md)
4. [03-contract-registry.md](03-contract-registry.md)
5. [04-principal-policy-and-run.md](04-principal-policy-and-run.md)
6. [05-request-lifecycle-and-slos.md](05-request-lifecycle-and-slos.md)
7. [06-authority-and-data-ownership.md](06-authority-and-data-ownership.md)
8. [07-provider-contract.md](07-provider-contract.md)
9. [08-context-and-memory-contract.md](08-context-and-memory-contract.md)
10. [09-memory-lifecycle-and-deletion.md](09-memory-lifecycle-and-deletion.md)
11. [10-evidence-contract.md](10-evidence-contract.md)
12. [11-operator-and-mcp-surfaces.md](11-operator-and-mcp-surfaces.md)
13. [12-async-intelligence.md](12-async-intelligence.md)
14. [13-security-invariants-and-test-gates.md](13-security-invariants-and-test-gates.md)
15. [14-failure-modes-and-readiness.md](14-failure-modes-and-readiness.md)
16. [15-runtime-operations-and-recovery.md](15-runtime-operations-and-recovery.md)
17. [16-compatibility-and-versioning.md](16-compatibility-and-versioning.md)
18. [17-roadmap-and-gates.md](17-roadmap-and-gates.md)
19. [18-gap-register.md](18-gap-register.md)
20. [19-references.md](19-references.md)
21. [20-product-strategy-gap-audit-and-recommended-redesign.md](20-product-strategy-gap-audit-and-recommended-redesign.md) (product strategy / gap audit research; does not supersede numbered contracts)

## Non-goals

This baseline does not authorize implementation of a new service, schema, provider adapter, write-capable tool, marketplace, graph accelerator, A2A federation, managed cloud, or model decision runtime. Those require the gates and ADRs defined here.

## Core thesis

IBEX is a governed runtime with six explicit planes:

- **Enforcement:** deterministic identity, scope, policy, admission, budget, provider selection, and streaming.
- **Context and memory:** typed, tenant-authorized data retrieval and bounded context compilation.
- **Provider:** deployment identity, capability negotiation, adapters, streaming, usage, and fallback.
- **Evidence and control:** canonical configuration, reservations, operations, outbox, retention, and recovery.
- **Operator surfaces:** versioned management API, Console/BFF, diagnostics, and compatibility-only Dashboard.
- **Async intelligence:** extraction, indexing, evaluation, and advisory models that cannot grant authority or perform irreversible effects.

The enforcement plane is the only synchronous authority for action admission. Models, retrieval scores, caches, memory text, tool descriptions, and provider responses never create authority.

## Required documentation change

A boundary-crossing code change must update this directory, the contract registry, the status ledger, security/test gates, relevant existing canonical docs, and an ADR when semantics change. Documentation is a release input, not post-release decoration.
