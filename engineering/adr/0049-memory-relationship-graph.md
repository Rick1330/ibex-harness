---
title: "ADR-0049: Memory relationship graph readiness"
description: "Architecture decision record 0049 — ibex_core.memory_relationships org-safe CREATE, bidirectional traversal indexes, supersession view, and depth-capped tip helper for Phase 2.5 Track E."
adrId: "0049"
status: "Accepted"
date: "2026-08-25"
authors: "IBEX Harness team"
---

::decision-banner{status="Accepted" date="2026-08-25" id="0049"}
::

# ADR-0049: Memory relationship graph readiness

- **Status:** Accepted
- **Date:** 2026-08-25
- **Authors:** IBEX Harness team
- **Milestone:** [2.5.G5.M3 Relationship graph readiness](/roadmap)

## Context

Phase 3 conflict / extraction writers will emit typed edges (`supersedes`, `contradicts`, …). Phase 5 recursive CTEs will walk supersession chains to resolve “current” memories. Track E ([2.5.G5](/roadmap)) must land graph-ready schema before those writers.

The milestone sketch assumed `memory_relationships` already existed and only needed a source-type index plus a helper view. Applied migrations through `000015` have **no** `memory_relationships` table. The DATABASE_SCHEMA draft used single-column FKs and non-FORCE RLS — insufficient for multi-tenant isolation ([ADR-0047](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0047-memory-temporal-validity.md)).

Edge semantics: **`supersedes` means source replaces target**. Resolving to the current tip from an older memory walks **incoming** supersedes (`target` → `source`), so a source-only index is incomplete.

## Decision

### 1) Greenfield CREATE (not index-only ALTER)

Ship `ibex_core.memory_relationships` in `000016_create_memory_relationships`. Phase 3.1.1 must **not** `CREATE TABLE memory_relationships` again (expand-only if columns are added later).

### 2) Tenancy-first DDL

- `org_id NOT NULL` → `organizations ON DELETE RESTRICT`
- Composite FKs `(source_memory_id, org_id)` and `(target_memory_id, org_id)` → `memories(id, org_id) ON DELETE CASCADE` (same-org edges enforced structurally)
- Taxonomy CHECK for the six relationship types (unchanged)
- `confidence NUMERIC(3,2) NOT NULL DEFAULT 0.90 CHECK (0..1)`
- `CHECK (source_memory_id <> target_memory_id)` (no self-loops)
- `UNIQUE (source_memory_id, target_memory_id, relationship_type)`
- `FORCE ROW LEVEL SECURITY` + `ibex_core.rls_org_visible(org_id)`

### 3) Bidirectional graph-traversal indexes

- `(org_id, source_memory_id, relationship_type)` — forward walks / “what did this replace?”
- `(org_id, target_memory_id, relationship_type)` — reverse walks / “resolve to current tip”

Org-leading keys serve service-account queries that filter by `org_id` explicitly (RLS bypass).

### 4) Helper view + tip function (schema readiness)

- View `ibex_core.memory_supersession_edges` — `relationship_type = 'supersedes'` projection with `security_invoker = true` (PG16) so caller RLS applies
- Function `ibex_core.resolve_supersession_tip(org_id, memory_id, max_depth DEFAULT 5)` — `SECURITY INVOKER`, `search_path` pinned, base case seeds from `memories` where `id` and `org_id` match (returns NULL when invisible/mismatched), `org_id` predicate at every recursion level, hard depth cap `1..5` (out-of-range returns start id), cycle break via path array; valid seed with no outgoing supersedes returns the start id

No application Go/Python writers in this milestone.

### 5) Non-goals

- No new edge types / taxonomy renames
- No Apache AGE or external graph database
- No backfill (empty table until Phase 3 writers)

## Consequences

### Positive

- Phase 3 can insert edges without inventing tenancy shape
- Phase 5 CTEs have indexes and a reference tip helper matching [5.B.1](/roadmap) constraints
- Cross-org edges fail closed at the FK layer

### Negative

- Sketch “table already exists / index-only” diverges (documented on the milestone)
- Branching supersession graphs make tip selection depth-primary then deterministic by id; writers should prefer chains

## Rollout

- Migration: `infra/migrations/postgres/000016_create_memory_relationships.{up,down}.sql`
- Down is dev/test only; production forward-only per ADR-0005

## References

- [ADR-0005](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0005-postgres-migration-strategy.md)
- [ADR-0047](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0047-memory-temporal-validity.md)
- [ADR-0048](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0048-memory-multi-label-categories.md)
- Milestone [2.5.G5.M3](/roadmap)
- Milestones [3.1.1](/roadmap), [3.C.3](/roadmap), [5.B.1](/roadmap)
