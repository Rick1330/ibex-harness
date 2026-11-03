# Agents page — design rationale

## Layout
List and detail share the same Investigate chrome as Sessions/Explore: page
title, filter strip with removable pills, hairline table rows (no card cage).
Detail stacks header → KPI strip → directive → config → cross-link tabs →
danger zone so operators scan status before editing policy.

## Typography
Compact operator density (11–13px body, 18px titles). Monospace reserved for
immutable slug, API field keys, and version hashes — not decoration.

## Color / status
Status badges use shape + icon in addition to color (filled active, outline
pause/archive) so status remains readable without relying on hue alone.
Destructive actions live only in a bordered danger zone, visually separate
from routine Activate/Pause.

## Components
- KPI strip reuses Overview’s serif numeral language for real counters only.
- Config form labels are the real `config` JSONB keys, with plain-language
  helpers beside them.
- Cross-link tabs deep-link into Sessions / Explore / Memories instead of
  cloning those UIs.
- Analytics tab is an honest empty state until `/stats` ships.

## Honesty
No invented health scores. Soft provider/model note for deferred registry
validation. Identical not-found for missing and cross-tenant agents. Delete
stays out of row actions and is blocked inline when `total_sessions > 0`.
