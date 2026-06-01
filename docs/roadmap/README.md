# IBEX Harness — Development Roadmap

Living plan for building IBEX Harness from the current foundation through the architecture described in [ARCHITECTURE.md](../ARCHITECTURE.md).

## How to read this roadmap

| Concept | Meaning | Typical size |
| --- | --- | --- |
| **Phase** | Major capability plateau; unlocks the next layer | 3–8 weeks (solo dev + AI) |
| **Goal** | Measurable outcome within a phase | 1–2 weeks |
| **Milestone** | PR-sized deliverable with tests and docs | 2–5 days |

Start with [CURRENT_STATE.md](CURRENT_STATE.md) for what works today and the next three tasks. Use [PHASES.md](PHASES.md) for the full timeline.

## Status legend

| Symbol | Meaning |
| --- | --- |
| Complete | Merged to `main`; exit criteria met |
| In Progress | Active branch or PR open |
| Planned | Not started; prerequisites documented |
| Blocked | Waiting on decision, dependency, or external factor |
| Deferred | Explicitly out of scope for the current phase |

## Branch and PR naming

Follow [DEVELOPMENT_GUIDE.md](../DEVELOPMENT_GUIDE.md) §6.1 and §6.1.1.

| Rule | Value |
| --- | --- |
| Milestone branch | `<type>/m{phase}-{goal}-{milestone}-{kebab-slug}` |
| Types | `chore` (migrations, proto, observability scaffolding); `feature` (auth/proxy behavior) |
| Ticket override | `feature/IBEX-####-same-slug` when a GitHub issue exists |
| PR title | Conventional commit + milestone tag, e.g. `chore(db): postgres migrations (m1.1.1)` |
| Scope | One milestone per branch (§6.2) |

Each milestone file under `phase-*/milestones/` lists its branch and an example PR title.

**Historical:** Foundation PRs used `chore/foundation-00N-*`; Phase 1+ uses the `m*` pattern above.

## Directory layout

```text
docs/roadmap/
  README.md              ← you are here
  CURRENT_STATE.md       ← update after every merged milestone
  PHASES.md              ← all phases at a glance
  FINDINGS.md            ← pivots and unexpected discoveries
  phase-N-*/             ← per-phase goals, milestones, risks
  prompts/               ← copy-paste milestone execution prompts
```

## Relationship to other docs

| Location | Role |
| --- | --- |
| [docs/](../) | Target system design (architecture, schema, APIs, security) |
| Session workspace | Sibling `ibex-harness-workspace/` (not in git) — see DEVELOPMENT_GUIDE §12 |
| `ibex-harness-workspace/archive/foundation/` | Closed implementation audits (001–005); historical only |
| [docs/adr/](../adr/) | Durable technical decisions |
| [prompts/](../../prompts/) | Reusable AI assistant prompt templates |

**Rule:** The roadmap describes *what to build next*. Docs describe *how the finished system behaves*. The workspace `archive/` records *what was merged* for past foundation work; do not treat it as the source of “next tasks.”

## How to update the roadmap

After each milestone merges to `main`:

1. Update [CURRENT_STATE.md](CURRENT_STATE.md) (SHA, works / not-works, next tasks).
2. Mark the milestone **Complete** in the phase `milestones/` file.
3. Refresh session workspace `current_state.md` and `handoff.md` (DEVELOPMENT_GUIDE §12.3).
4. Log surprises in [FINDINGS.md](FINDINGS.md) if the plan changed.
5. Add ADRs under `docs/adr/` when introducing new tools, directories, or contracts.

Do not rewrite closed archive audits; link forward from roadmap instead.

## Implementation history (Foundation)

Foundation work is complete. See [phase-0-foundation/completed.md](phase-0-foundation/completed.md). Archived audits **001–005** live in the session workspace at `archive/foundation/` (not in this repository).
