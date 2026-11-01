---
title: "ADR-0089: Memory/context product shape and Console scope"
description: "Architecture decision record 0089: lock IBEX to a memory/context-first, platform-expandable product shape; narrow the Console to the agent → session → memory → evidence lifecycle with a separate platform tier; permit clearly labelled illustrative previews; and adopt a supported bundle plus a platform release manifest instead of per-service versions."
adrId: "0089"
status: "Accepted"
date: "2026-11-01"
authors: "Elshaday Mengesha (@Rick1330)"
---

::decision-banner{status="Accepted" date="2026-11-01" id="0089"}
::

# ADR-0089: Memory/context product shape and Console scope

- **Status:** Accepted
- **Date:** 2026-11-01
- **Author:** Elshaday Mengesha (@Rick1330)
- **Amends:** [ADR-0088](0088-console-nuxt-shadcn-vue-migration.md) §3 (live/preview boundary) and §5 (fixture removal). The Nuxt/Nitro stack decision in §1–§2 is unchanged.
- **Related:** [ADR-0078](0078-operator-runtime-topology.md), [ADR-0080](0080-ibex-console-service-rename.md), [ADR-0087](0087-public-site-nuxt-docus-migration.md).

## Context

The repository currently tells four product stories that do not agree:

1. `README.md` lists three capabilities — memory, context assembly, secure proxying — with no wedge.
2. The public site sells **self-hosted memory and context for AI agents**, with the OpenAI-compatible proxy as the adoption surface.
3. `engineering/architecture-v2/20-product-strategy-gap-audit-and-recommended-redesign.md` describes a four-plane agent control plane.
4. The Console designs **18 surfaces** across monitor, investigate, govern, spend, connect, and admin — an observability and governance product.

The Console is high-quality work, but it was designed against the broadest story while the public site and the status ledger describe the narrowest one. That mismatch is the source of the "the backend is behind" feeling: the Console designed 15 surfaces with no live read model, while the management API already exposes real routers for about half of them.

Two further conflicts make the drift expensive:

- **Preview policy.** ADR-0088 §3 forbids preview surfaces from rendering fixture rows, fake tenants, or fake credentials. The Console renders exactly those, labelled "Illustrative". The status ledger calls Console workflows "fixture-only or deferred". Two accepted documents disagree, and a machine check cannot enforce either.
- **Surface status.** Surface status is declared in at least three places — `services/console/shared/operator/surfaces.ts`, `services/console/README.md`, and the status ledger — and they do not agree. Settings is documented as "Live D1" and is a preview fixture. The README says there is no preview-data mode while `console-demo.ts` exists.

Packaging has the same shape of problem. "Use only the memory service" is not a toggle today: memory requires AuthService gRPC, the Embedder, PostgreSQL with pgvector, and migrations. The Helm chart is a single umbrella with no per-service enable flags, and the release model is one platform version with per-service images but no compatibility manifest.

## Decision

### 1. Product shape: memory/context-first, platform-expandable

IBEX is the self-hosted memory and context layer for multi-tenant agents.

- **Promise:** point an agent at an OpenAI-compatible endpoint or add the MCP server. IBEX resolves tenant and agent identity, injects bounded context, stores governed memories, and attaches evidence to every request.
- **Primary user:** the platform or security team supporting several agent applications.
- **Console role:** the operations plane for the memory/context lifecycle, not a general observability product.
- **Expansion rule:** budgets, evidence depth, drift, incidents, and analytics become product surfaces only when a named design partner needs them. A designed page is not a demand signal.

The proxy stays a first-class runtime component and the adoption surface. It is not the product differentiator, and this record does not demote it.

### 2. Console scope: core tier and platform tier

The Console has exactly two static tiers. Every surface declares one.

**Core tier (10 surfaces, the default Console):**

| Surface | Route | Availability | Role in the lifecycle |
| --- | --- | --- | --- |
| Overview | `/` | live | Organization snapshot and current health |
| Agents | `/agents` | preview | Who writes and reads memory |
| Sessions | `/sessions` | preview | The conversation scope |
| Memories | `/memories` | preview | What is stored, retrieved, and forgotten |
| Evidence | `/evidence` | preview | What is certified, redacted, or tombstoned |
| Directives | `/directives` | preview, deferred | The standing half of injected context |
| Policies | `/policies` | preview | The rules in force for context and memory |
| Explore | `/explore` | live | Read-only request traces |
| Platform | `/platform` | live | Dependency, ingestion, and recovery health |
| Settings | `/settings` | preview | Organization configuration and boundaries |

Directives is core because context injection is directive plus memory. A Console for a context product that cannot show directives cannot explain the product. It has no owning API router yet, so it is core-tier but `deferred`; it does not count toward the live ratio until a contract exists.

**Platform tier (8 surfaces, hidden from the default navigation):**

Incidents, Drift, Audit, Budgets, Analytics, Providers, MCP tools, Access.

These remain in the repository as designed previews. They are not deleted, not promoted, and not part of the default Console navigation. They are reachable only through an explicit "Platform tier" disclosure and carry a persistent tier banner. Promoting one requires a named design partner, an owning contract, and a superseding ADR — not merely a read model.

**Information architecture:**

- **Lifecycle:** Overview, Agents, Sessions, Memories, Evidence
- **Context:** Directives, Policies
- **Investigate:** Explore
- **Operate:** Platform, Settings
- **Platform tier** (collapsed): the eight surfaces above

**Sequencing rule:** core-tier surfaces are wired before platform-tier surfaces, even when a platform-tier surface has a cheaper read model. The next live slices are Agents, Policies, and Settings; then Sessions, Memories, and Evidence. Access, Providers, and Budgets wait behind the core lifecycle.

### 3. Surface lifecycle and freeze

A surface has two independent attributes: **availability** (what it may render) and **acceptance** (what the status ledger certifies).

**Availability** moves through four states, in order:

1. `preview` — design only; no owning contract; no live claim.
2. `read-model` — owning contract exists; the operator projection is implemented and tested; the surface stays preview until the BFF reads it.
3. `live` — the surface reads its owning contract through the BFF, renders real data, fails closed, and has no fixture fallback.
4. `write-gated` — live plus a mutation path with CSRF, audit, idempotency, and a privileged-write affordance.

`live` is an availability label, not an acceptance claim. Acceptance is the separate status-ledger axis (`provisional`, `accepted`, and so on). A live surface remains `provisional` until tenant-negative tests, accessibility checks, and hosted evidence exist, and the UI must not present `live` as certification.

**Freeze:** no new surface may be added to either tier until at least five core surfaces are live and every core surface has an owning API contract rather than a contract name. The live ratio is computed from `SURFACES`, not from prose.

### 4. Preview policy (amends ADR-0088 §3)

Preview surfaces **may** render illustrative fixture rows. ADR-0088 §3's blanket prohibition is replaced by the following conditions. All of them are mandatory:

1. The surface is statically `preview`. A `live` surface never renders fixture data and fails closed instead.
2. The page renders a persistent, non-dismissible `Illustrative preview` banner above the first fixture, and the page verdict states the coverage, for example `0% live · illustrative only`.
3. Fixture rows are visibly marked as illustrative at the row or table level. A reader must not need the banner to know a row is not evidence.
4. Fixture tenant identifiers use the reserved prefix `org_demo_` where the contract is a string id, or the reserved demo UUID `00000000-0000-4000-8000-000000000000` where the contract requires a UUID. They are never a seeded development org or a realistic customer identifier.
5. Fixture modules live in `services/console/app/lib/*-preview.ts`, are registered in one enumerable fixture registry, and are importable only by preview surface components. The shared shell, layouts, and live pages must never import a fixture module.
6. Fixtures never contain credentials, tokens, keys, real personal data, or anything that could be mistaken for a secret.
7. A preview page never claims that its contract is implemented, and never presents fixture output as evidence.

**Development demo mode.** `CONSOLE_DEMO_ENABLED` may substitute illustrative reads for live-shaped contracts only when `import.meta.dev` is true. Demo mode must render the `Illustrative` provenance chip, must not activate in a production build, and is not a data mode. `CONSOLE_DATA_MODE` remains a presentation flag and never enables fixtures.

**Enforcement.** A unit test enumerates the fixture registry, asserts conditions 4 and 5, and fails if the shared shell or a live page imports a fixture module. The production end-to-end suite asserts fail-closed behavior with no fixtures.

### 5. Packaging: one supported bundle now, library-first later

- **Now:** a tested `memory-context` bundle profile — memory, AuthService, Embedder, PostgreSQL with pgvector, and migrations — documented as a **supported bundle with explicit limits**, not a standalone service.
- **Helm:** infrastructure toggles only (bundled PostgreSQL, Redis, ClickHouse, MinIO). No per-application-tier `enabled` flags.
- **Library-first extraction** (`ibex-memory-core` or a minimal memory server with its own schema) is the correct path if memory-only adoption becomes a real product goal. It does not start without an external consumer.
- **Componentized chart:** not adopted. It pays off only when a component must scale independently; IBEX has no such pressure, and per-tier versions would add skew and migration ordering for no adoption gain.
- **Per-service semver:** not adopted. One platform version remains.

The bundle must document included images and digests, required and optional dependencies, upgrade order and migration range, and what is **not** claimed: no hard budgets without the ledger, no durable evidence without the outbox and relay, no tenant-wide memory without AuthService.

### 6. Release: platform train plus a compatibility manifest

- release-please runs in **manifest mode** with one package `"."` and `component: "platform"`, keeping `include-component-in-tag: false` so existing `v0.1.x` tags resolve.
- Each release publishes `release-manifest.json` containing the platform version, every image digest, contract and schema versions, the migration range, supported bundles, and each bundle's smoke-test status.
- Images are deployed by **digest**. Tags are pointers, not artifacts.
- A platform tag without a manifest is an incomplete release.

Changing `.github/workflows/**` and the release configuration requires owner approval under `AGENTS.md` §10. This record sets the direction; it does not authorize the workflow edit by itself.

### 7. One surface-status source

`services/console/shared/operator/surfaces.ts` is the machine-readable source of truth for surface key, route, tier, availability, domain, phase, group, and owning contract.

A `surface-status` check cross-validates it against:

- `services/console/README.md` — exactly one row per surface, with a matching live/preview claim and tier placement;
- `engineering/architecture-v2/00-status-and-evidence.md` — the Console rows agree on the core live count, core preview count, and platform-tier count, and cite this record;
- `site/app/data/ledger.ts` and the published status page — the same three counts and the same citation.

The check does not parse free-form ledger prose beyond those counts. Prose may add detail; it may not contradict `SURFACES`.

## Consequences

- The Console's default navigation shrinks from 18 surfaces to 10. Eight designed surfaces remain available but are explicitly platform-tier.
- The Console stops presenting itself as an observability product. Incidents, drift, analytics, and budgets are no longer part of the default product story.
- Preview fixtures become legal, bounded, labelled, and machine-checked. The design work is preserved instead of deleted.
- Documentation must use the Nuxt 4 / Nitro stack and the tier model. Next.js claims are stale and must be corrected.
- The next live work is the core lifecycle, not the cheapest available read model.
- Packaging claims stay honest: a bundle is supported only when its smoke test passes.
- Release answers "what is actually running?" through a digest manifest rather than a tag.
- The status ledger and the Console README become derived claims that a check can reject.

## What this record does not decide

- It does not add login, mutation, or write-gated flows.
- It does not delete platform-tier routes or fixtures.
- It does not accept any D3–D6 contract.
- It does not authorize workflow, branch-protection, or release-configuration edits.
- It does not claim hosted deployment, HA, or measured SLOs.

## Rollback

The tier model, navigation, and documentation are reversible by reverting the implementing commit. No data migration, no persistent-store change, and no API contract change is involved. Fixture renames are local to the Console. Reverting restores the prior 18-surface navigation and the ADR-0088 §3 prohibition.

## References

- [ADR-0088](0088-console-nuxt-shadcn-vue-migration.md) — Console stack; §3 and §5 amended here.
- [ADR-0087](0087-public-site-nuxt-docus-migration.md) — public-site Nuxt migration.
- [ADR-0080](0080-ibex-console-service-rename.md) — Console name and service boundary.
- [`services/console/shared/operator/surfaces.ts`](../../services/console/shared/operator/surfaces.ts) — surface source of truth.
- [`engineering/architecture-v2/00-status-and-evidence.md`](../architecture-v2/00-status-and-evidence.md) — runtime claim ledger.
- [`engineering/OPERATOR_PLATFORM_ARCHITECTURE.md`](../OPERATOR_PLATFORM_ARCHITECTURE.md) — Console boundary.
