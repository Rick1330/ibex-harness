---
title: Reference
description: Glossary, roadmap, compatibility policy, and decision-record index.
audience: evaluator
status: PROVISIONAL
scope: provisional
verifiedDate: "2026-10-21"
sourceOfTruth: engineering/architecture-v2; engineering/adr
---

::page-status{status="PROVISIONAL" verified="2026-10-21" note="Reference material is stable; compatibility and gate acceptance remain provisional"}
::

Use this section for terminology and historical context. Reference pages do not expand runtime claims.

## Pages

- [Glossary](/docs/reference/glossary) — terms used across the platform.
- [Roadmap and gates](/docs/reference/roadmap) — the implementation sequence and gate definitions.
- [Compatibility and versioning](/docs/reference/compatibility) — supported surfaces, version axes, and breaking-change rules.
- [Architecture decisions](/docs/reference/adr) — how to read ADRs and where to find them.

## How to read claims

| Term | Meaning |
| --- | --- |
| Shipped-local | Implemented and locally evidenced; not hosted or production-ready |
| Provisional | Seam or contract exists; evidence or review remains open |
| Proposed | Design only; no runtime or acceptance evidence |
| Deferred | Intentionally outside the current dependency set |
| Accepted contract shape | Text and safety semantics accepted; does not imply runtime completion |

An ADR explains a choice. It is not evidence that the choice is implemented. The status ledger is the authoritative claim surface.
