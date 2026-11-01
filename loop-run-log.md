# Loop Run Log — IBEX Harness

Append one entry per run. Prune entries older than 30 days.

## Format

```json
{
  "run_id": "2026-06-09T08:15:00Z",
  "pattern": "daily-triage",
  "duration_s": 45,
  "items_found": 4,
  "actions_taken": 1,
  "escalations": 0,
  "tokens_estimate": 52000,
  "outcome": "report-only | fix-proposed | escalated | no-op"
}
```

`outcome` must be one of: `report-only`, `fix-proposed`, `escalated`, `no-op`.

## Recent Runs

```json
{
  "run_id": "2026-10-31T00:00:00Z",
  "pattern": "daily-triage",
  "duration_s": 240,
  "items_found": 8,
  "actions_taken": 0,
  "escalations": 1,
  "tokens_estimate": 42000,
  "outcome": "report-only"
}
```

Notes: first run. `duration_s` and `tokens_estimate` are self-reported estimates; `run_id` is date-precision because no shell/clock was available at L1. Escalation = loop has no CI/issue visibility (STATE.md High Priority #1).
