# Loop Safety Model — IBEX Harness

This file describes how loop-driven changes are bounded. It complements `AGENTS.md` (project rules),
`loop-constraints.md` (binding per-run rules), and `LOOP.md` (what runs at which level).

## Levels

| Level | Allowed | Requires |
|-------|---------|----------|
| L1 report-only | Read, triage, update `STATE.md` and `loop-run-log.md` | Nothing beyond this scaffold |
| L2 isolated fix | One scoped fix per item in a `git worktree`, then verifier | Verifier verdict, human-approved PR |
| L3 unattended | Scheduled runs with human gates | Proven L1/L2 runs, `gate.yaml`, proven `loop-drill`, filled budget |

L1 is the current level. Nothing in this repo may promote a loop to L2/L3 automatically.

## Denylist

The `implementer` agent denies edits to:

- `.env`, `.env.*`
- `auth/**`, `secrets/**`, `credentials/**`, `payments/**`

Any change to these paths escalates to a human. Denying at the agent level means the tool call fails
before the edit happens; it is not advisory.

## Human gates

- No push, merge, or PR creation without human approval.
- No change to a public API contract, database migration, or tenant-isolation logic without human approval.
- No self-approval of budget increases. `loop-budget.md` is human-edited only.
- `loop-pause-all` in `STATE.md` stops every loop immediately.

## MCP scopes

- L1 uses no MCP servers.
- L2+ may use GitHub MCP with **read + comment** scope only.
- No unattended loop may hold a connector with write scope.

## Maker/checker split

- `implementer` proposes a change; `verifier` (and the `loop-verifier` skill) approves or rejects it.
- The verifier never edits files and never approves on the promise of a follow-up fix.
- A REJECT discards the worktree; a second attempt starts clean.

## Budget and circuit breaking

- Caps live in `loop-budget.md`; the kill switch is `loop-pause-all`.
- For L2+, run `loop-context --check --ledger loop-ledger.json` before each retry; exit `2` escalates to a human.
- Max 3 fix attempts per item, then escalate.

## What this model does not claim

Worktree isolation is not container isolation. Processes still have OS-level filesystem and network access.
Inspect any generated patch before applying it.
