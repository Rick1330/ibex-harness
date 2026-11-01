# Loop Configuration — IBEX Harness

Loop state lives in `STATE.md`. Binding rules live in `loop-constraints.md` and `AGENTS.md`.
This file describes **what runs and at what level**; it must stay in sync with `STATE.md`.

## State

state: STATE.md

## Active Loops

| Pattern | Cadence | Status | Command |
|---------|---------|--------|---------|
| Daily Triage | 1d | L1 report-only | `opencode run "Run loop-triage. Read STATE.md first. Update High Priority and Watch List. No auto-fix in week one." --agent loop-triage` |

## Levels

- **L1 (current)** — report only. Reads, triages, and updates `STATE.md` / `loop-run-log.md`. No code edits, no shell.
- **L2 (not enabled)** — one scoped fix per item in an isolated `git worktree`, followed by the `verifier` agent.
- **L3 (not enabled)** — unattended operation. Requires proven L1/L2 runs, `gate.yaml`, a proven `loop-drill`, and a filled `loop-budget.md`.

Do not promote a loop past its recorded level without the human gates below.

## Human Gates

- No auto-fix until the L2 checklist is complete and recorded in `STATE.md`.
- No push, merge, or PR without human approval.
- Denylisted paths (`.env*`, `auth/`, `secrets/`, `credentials/`, `payments/`) are blocked in `implementer.md` and must never be auto-edited.
- Any change to a public API contract, database migration, or tenant-isolation logic escalates to a human.
- `loop-pause-all` in `STATE.md` stops every loop immediately.

## Worktrees

- L2+ fix attempts use one explicit `git worktree` per attempt, run with `opencode run --dir <worktree>`.
- One worktree per fix attempt; discard after a `VERDICT: REJECT`.
- Never run a fix attempt in the primary checkout.

## Research before a fix

Before proposing an L2 fix, check the current library documentation (Context7) and, when a competitor or upstream
project already ships the behaviour, study their design (DeepWiki). Record the sources in the handoff so the verifier
can check that the fix matches how the API actually works today.

## Resource policy

The quality scanners are heavy and are **off by default**. The loop must not leave them running.

- L1 triage: read-only. Call `local_mcp_status`, report RAM and server state, enable nothing.
- L2 review: call `local_mcp_enable` immediately before verification and `local_mcp_disable` immediately after.
- At 90% RAM the `resource-guard` plugin disables the heavy servers automatically; the user timer
  `infra/scripts/memory-guard.sh` does the same when OpenCode is not running.
- Remote servers (Exa, Context7, DeepWiki) cost no local memory and stay connected.

## Logs

CI and test logs are captured raw first, then compressed for reading:

```bash
gh run view <run-id> --log-failed > /tmp/loop-ci.log
caveman shrink -- cat /tmp/loop-ci.log
```

The raw file stays available as evidence; the compressed view is what the agent reads. Never cite a compressed excerpt
as the complete result.

## Connectors (MCP)

- L1 needs no MCP servers.
- For L2+, GitHub MCP may read CI status and issues; scope it to read + comment until the loop is trusted.
- Do not grant write scopes to any connector used by an unattended loop.

## Budget

- Daily cap and run cap are defined in `loop-budget.md`.
- Max sub-agent spawns per run: 0 at L1, 2 at L2.
- If token spend reaches 80% of the daily cap, switch to report-only.
- Estimate before scheduling: `npx @cobusgreyling/loop cost --pattern daily-triage --level L1 --cadence 1d`.

## Scheduling (not enabled)

The loop is scaffolded but **no timer is installed**. To enable a daily 08:00 run:

```cron
0 8 * * * cd /home/rick/dev/ibex-harness && opencode run "Run loop-triage. Read STATE.md first. Update High Priority and Watch List. No auto-fix in week one." --agent loop-triage >> .loop-run.log 2>&1
```

Review `.loop-run.log` and `STATE.md` after the first two runs before trusting the cadence.

## Health checks

```bash
npx @cobusgreyling/loop doctor .          # audit + sync + top 3 actions
npx @cobusgreyling/loop sync .            # STATE.md <-> LOOP.md drift
npx @cobusgreyling/loop audit . --suggest # Loop Ready score
```

The loop skills live in `.claude/skills/`, a project skill source OpenCode discovers and `loop-audit` scans.
(OpenCode's native `.opencode/skills/` would also work, but `loop-audit` does not scan that path, so its health checks
would report the skills as missing.)

## Links

- Agent operating rules: `engineering/agent-playbook.md`
- Loop constraints: `loop-constraints.md`
- Project agent guide: `AGENTS.md`
- Engineering docs: `engineering/`
- Upstream pattern: <https://github.com/cobusgreyling/loop-engineering/blob/main/patterns/daily-triage.md>
- Upstream checklist: <https://github.com/cobusgreyling/loop-engineering/blob/main/docs/loop-design-checklist.md>
- Upstream safety model: <https://github.com/cobusgreyling/loop-engineering/blob/main/docs/safety.md>
