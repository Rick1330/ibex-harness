# IBEX Harness — UI/UX Guidelines (Dashboard)

## 1) Purpose

The IBEX Dashboard is an operator console for:

- sessions and replay,
- memory inspection and management,
- directive versioning and diffs,
- drift alerts and behavioral fingerprints,
- analytics and billing.

This is a dense data UI. Consistency and clarity matter more than flourish.

This document defines:

- information architecture principles,
- component guidelines,
- accessibility requirements,
- loading/error/empty state standards,
- and data visualization conventions.

---

## 2) UX Principles

### U1 — Debuggability is the primary UX goal

The user’s main question is often:

> “Why did my agent do that?”

The UI must make it easy to trace:

- directive version
- context injection
- memories used and their scores
- tool calls
- time and token usage

### U2 — Consistency beats cleverness

Repeated patterns should be visually and behaviorally identical:

- tables
- filters
- date range pickers
- pagination
- copy-to-clipboard behavior
- code blocks

### U3 — Progressive disclosure

Default views show summaries; deep details expand on demand:

- trace summary first, full JSON behind “View raw”
- memory content preview first, full content on open
- drift summary first, per-feature drift details on expand

### U4 — Every state is designed

Every data view must have:

- loading state
- empty state
- error state
- success state

No blank screens.

---

## 3) Information Architecture (Top-level)

Recommended nav:

- Agents
- Sessions
- Traces
- Memories
- Directives
- Drift Alerts
- Analytics
- Billing
- Settings / Org

Cross-links:

- from trace → session → agent
- from trace → memories used
- from directive version → sessions that ran under it
- from drift alert → traces that contributed

---

## 4) Design System Basics (Tailwind-driven)

### 4.1 Spacing and sizing

- Use Tailwind spacing scale (4px grid).
- Avoid arbitrary values unless justified.

### 4.2 Typography

- Base: `text-sm` for dense UI
- Headings:
  - page title: `text-xl font-semibold`
  - section title: `text-base font-semibold`
- Code: `font-mono text-xs` for IDs/hashes

### 4.3 Color usage

- Use semantic colors:
  - success: green
  - warning: amber/yellow
  - error: red
  - info: blue
- Avoid using color alone to encode meaning (accessibility).
  - always pair with icon or label.

### 4.4 Component primitives (must exist)

- Button (primary/secondary/danger/ghost)
- Input, Textarea
- Select
- Badge (status)
- Card
- Table
- Tabs
- Modal/Drawer
- Toast/Notification
- Skeleton (loading)
- EmptyState
- ErrorState

---

## 5) Accessibility (WCAG 2.1 AA target)

### 5.1 Keyboard navigation

- All interactive elements reachable via Tab
- Focus visible styles required
- Modal traps focus; ESC closes modal
- Enter/Space activates buttons

### 5.2 ARIA rules

- Use `aria-label` for icon-only buttons
- Use `role="alert"` for error banners
- Use `aria-busy` for loading states
- Use `aria-expanded` for expandable panels

### 5.3 Color contrast

- Ensure text meets AA contrast
- Avoid low-contrast grays for important info

### 5.4 Tables

- Column headers use `<th scope="col">`
- Row headers if needed use `<th scope="row">`
- Sort controls must be keyboard accessible and announce state

---

## 6) Data View Standards (Tables/Filters/Pagination)

### 6.1 Filtering

Every list page should support:

- search (full-text or id search as appropriate)
- date range (for traces/sessions)
- status filter (active/failed/etc.)
- tag filter (agents/memories)
- org scope implied from session

### 6.2 Pagination

- cursor-based pagination UI:
  - “Next” and “Previous”
  - show “Showing X–Y of Z”
- page size options (20/50/100) if data heavy

### 6.3 Empty states

Empty state must:

- explain why it’s empty
- suggest next action
  - “Create your first agent”
  - “Run your agent to generate sessions”
  - “Enable memory extraction”

---

## 7) “Why Did My Agent Do That?” View (Trace Inspector Spec)

The trace inspector is the core debugger.

It must show:

1. Summary header:
   - agent, session, model, provider
   - total latency, proxy overhead, context time
   - prompt/completion tokens
2. Context assembly:
   - directive version id + hash
   - token budget breakdown (directive/history/memory/tools)
   - memories injected list:
     - rank
     - composite score + components
     - category, confidence, usefulness
3. Conversation:
   - request messages (collapsed by default)
   - response content (streamed if applicable)
4. Tool calls:
   - tool name + args
   - idempotency key
   - status/outcome
5. Raw JSON:
   - sanitized payload (no secrets)
6. Links:
   - memory detail pages for injected memories
   - directive diff view for current directive
   - session replay to see timeline

Security:

- raw prompt/response view must be permission-gated
- audit log entry for viewing sensitive data (enterprise tier option)

---

## 8) Drift Alerts UX

Drift alert page must show:

- severity (low/medium/high)
- impacted agent + timeframe
- top drifted features:
  - current vs baseline
  - z-score / distance
- suggested actions:
  - review directive changes
  - inspect recent traces
  - reset baseline (if admin)
  - pause agent (if high severity)

Avoid alert fatigue:

- group alerts by agent and time window
- allow acknowledgement and resolution notes

---

## 9) Directive Management UX

Directive pages must include:

- version timeline (like git log)
- version statuses (draft/review/active/deprecated/revoked)
- diff viewer:
  - unified and split mode
  - token delta
- regression scenarios list:
  - critical scenarios highlighted
  - last run results
- promotion workflow:
  - submit review → run regression → approve → promote
- emergency revoke:
  - confirmation + MFA gate

---

## 10) Charting Guidelines

### 10.1 Choose the simplest chart that answers the question

- latency distribution: histogram
- token usage over time: line chart
- tool usage distribution: stacked bar or pie (sparingly)
- drift features: small multiples line charts

### 10.2 Performance constraints

- charts should render fast
- avoid huge DOM nodes; use canvas-based rendering if needed at scale
- limit points shown; aggregate by time bucket

### 10.3 Tooltip and legend rules

- tooltips must include units (ms, tokens)
- legend must be clickable to isolate series
- color mapping must be consistent across pages

---

## 11) Error Handling UX

### 11.1 Errors must be actionable

Display:

- human message
- request_id
- “Copy request ID”
- “Retry” action
- link to docs if known error code

Do not display:

- stack traces in production UI
- raw backend exception strings

### 11.2 Rate limit errors

If 429:

- show retry time (“Try again in 45s”)
- show upgrade prompt if quota-limited

---

## 12) Loading UX

- Use skeletons for list views (simulate table rows)
- Use spinners only for small localized actions
- Avoid full-page spinners unless necessary

---

## 13) UI Code Quality Rules (enforced culturally + lint)

- component file ≤ 200 lines
- max 8 props (prefer composition/context)
- avoid prop drilling beyond 2 levels
- no `any`, no unsafe casts
- server/client boundary respected (App Router)

---

## 14) UX QA Checklist (before merge)

For any UI change:

- [ ] keyboard navigation works
- [ ] focus visible everywhere
- [ ] loading/empty/error states present
- [ ] error messages actionable
- [ ] responsive behavior acceptable
- [ ] no secrets in client bundle (env vars)
- [ ] perf acceptable (no big bundle jump)

---

These guidelines are part of system quality: operators rely on the dashboard to trust and debug agents.
