---
title: "ADR-0090: Retire the dashboard compatibility shell"
description: "Architecture decision record 0090: remove services/dashboard and its manual Cloudflare Pages workflow; the canonical Console is the only operator application, and legacy /dashboard paths remain as redirects."
adrId: "0090"
status: "Accepted"
date: "2026-11-01"
authors: "Elshaday Mengesha (@Rick1330)"
---

::decision-banner{status="Accepted" date="2026-11-01" id="0090"}
::

# ADR-0090: Retire the dashboard compatibility shell

- **Status:** Accepted
- **Date:** 2026-11-01
- **Author:** Elshaday Mengesha (@Rick1330)
- **Supersedes:** the retention direction for `services/dashboard` in [ADR-0080](0080-ibex-console-service-rename.md) and [ADR-0088](0088-console-nuxt-shadcn-vue-migration.md).
- **Related:** [ADR-0078](0078-operator-runtime-topology.md), [ADR-0089](0089-product-shape-and-console-scope.md).

## Context

`services/dashboard` is a static 4.P.0 compatibility shell. It was kept during the Console migration as a fallback for connection state, credentialed API fetch, CSRF/login-body encoding, and operator-event SSE parsing. It was never the canonical product, and its README says it must not be expanded into a second production-intended dashboard.

The shell has no production deployment claim. Its only workflow, `operator-deploy.yml`, is a manual `workflow_dispatch` preview deploy to Cloudflare Pages, explicitly blocked until the API has a real ingress. It builds a static artifact and performs a single HTTP smoke check. It does not exercise authentication, tenant isolation, or the operator contracts.

Keeping it has a real cost:

- it is a second operator implementation in the workspace and in dependency, Codacy, and documentation inventories;
- it uses Next.js-era names (`NEXT_PUBLIC_API_BASE_URL`) that no longer describe the product;
- it competes with the canonical Console for the word "dashboard" and produces contradictory status statements;
- it has no owner, no acceptance evidence, and no promotion path.

The owner has decided to retire it rather than carry it indefinitely.

## Decision

1. Delete `services/dashboard` and `.github/workflows/operator-deploy.yml`.
2. Remove the workspace, Codacy, CI, and documentation references.
3. Keep the `/dashboard` and `/dashboard/*` redirects in `services/console` so old bookmarks reach the approved top-level routes.
4. Treat `services/console` as the only operator application. No replacement shell is created.

## What this record does and does not claim

- It **does not** claim that the compatibility shell reached parity with the Console, or that a parity matrix, hosted two-tenant evidence, or a rollback window exists. The shell had no production deployment, so no production runtime is retired.
- It **does not** claim that the canonical Console is production-ready. Its status remains the provisional boundary in the status ledger.
- It **does** record that the shell's preview-only deploy path is removed and that its tests no longer count as operator evidence.

This is an owner-directed retirement of a non-production compatibility artifact, not a production decommissioning.

## Consequences

- One operator application, one set of contracts, and one status story.
- The workspace and Codacy inventories shrink; the dashboard tests disappear.
- Old `/dashboard` URLs still redirect through the Console.
- Any future operator UI must be built in `services/console`; a second shell requires a new ADR.
- Historical planning documents that mention `services/dashboard` remain as records. They must not be read as current instructions.

## Rollback

Revert this change to restore the static shell and its manual preview workflow. There is no data migration, no persistent-store change, and no public contract change. Reverting does not restore a production deployment, because none existed.
