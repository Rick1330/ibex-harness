# Analytics — design rationale

Built against the documented `/v1/analytics/{overview,latency,memory-performance}`
shapes and ClickHouse `usage_facts` bucketing (`toStartOfHour`). No invented
metrics (no SLA score, no reconciled cost on this page).

## Layout

Single scroll column, investigation density matching Explore/Drift: period +
agent filter strip, KPI row, then trend | model, agents, latency, slow traces,
memory. KPI cards stay flat (no gradient fills) with mono tabular figures and
small trend deltas — same visual weight language as the overview shell, but
cardized so partial-data badges can sit per-field.

## Charting

Shared `MetricTrend` language (from Drift fingerprint history): bordered
metric panels, dashed reference lines, sparse event dots, 1.75px strokes,
mono 10px ticks.

- **Requests/tokens**: dual MetricTrend panels; partial ClickHouse buckets
  marked destructive (not silent gaps).
- **Latency percentiles**: p50→p95→p99 as MetricTrend per stage; p95 target
  as dashed rule; provider split from gateway stages.
- **Model distribution**: bordered share panel + mono legend.
- Overview / Billing burn-down reuse the same component.

## Honesty

- `estimated_cost_usd` labeled **Est. cost** / advisory / muted — ledger
  `actual_cost_cents` belongs on Usage/Cost (4.D.6).
- `completeness: partial` surfaces as an amber **partial data** badge on
  affected KPIs and the latency panel; never omitted.
- `empty_result_rate` warns above 5% — operational signal, not flat chrome.
- Top-agents rows omit cost unless/until the API returns it (backend sorts by
  cost internally; documented `top_agents` rows do not include it).
- 403 (`trace:read`) is a distinct state from endpoint failure.

## Typography

Mono for IDs, rates, and axis labels (11–12px); UI sans for section titles
(13px medium). No marketing display faces on this operate surface.
