# Loop Budget — IBEX Harness

> Primary loop: **Daily Triage** (L1 report-only)

## Daily limits

| Loop | Max runs/day | Max tokens/day | Max sub-agent spawns/run |
|------|--------------|----------------|--------------------------|
| Daily Triage | 2 | 100k | 0 (L1) / 2 (L2) |

## On budget exceed

1. Pause the scheduler (disable the cron entry or systemd timer).
2. Append an event to `loop-run-log.md`.
3. Notify a human via `STATE.md` High Priority.

## Kill switch

- Flag: `loop-pause-all` written into `STATE.md`.
- Resume only after a human clears the flag in `STATE.md`.

## Estimate spend

```bash
npx @cobusgreyling/loop cost --pattern daily-triage --level L1 --cadence 1d
```

## Rules

- Agents must never raise their own token cap. A human edits this file.
- Budget negotiation is a human-gated request appended to `STATE.md`, never a self-grant.
