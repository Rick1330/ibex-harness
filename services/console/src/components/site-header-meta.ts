export type PageMeta = { section: string; page: string; search: string }

type MetaRow = readonly [prefix: string, exactDetail: boolean, section: string, page: string, search: string]

const DEFAULT_META: PageMeta = {
  section: "Overview",
  page: "Overview",
  search: "Search metrics, agents, sessions...",
}

/** Longest-prefix first. exactDetail requires `/…/{id}` rather than the list route. */
const META_ROWS: readonly MetaRow[] = [
  ["/dashboard/explore/t/", false, "Investigate", "Trace Inspector", "Jump to span, memory, request..."],
  ["/dashboard/agents/", true, "Investigate", "Agent Detail", "Jump to sessions, directive..."],
  ["/dashboard/agents", false, "Investigate", "Agents", "Search agent name, directive..."],
  ["/dashboard/sessions/", true, "Investigate", "Session Timeline", "Jump to turn, memory, checkpoint..."],
  ["/dashboard/sessions", false, "Investigate", "Sessions", "Search session_id, agent, tag..."],
  ["/dashboard/memories/", true, "Investigate", "Memory Detail", "Jump to lineage, session..."],
  ["/dashboard/memories", false, "Investigate", "Memories", "Search memory_id, category..."],
  ["/dashboard/directives/", true, "Govern", "Directive Detail", "Jump to version, scenario, ledger..."],
  ["/dashboard/directives", false, "Govern", "Directives", "Search directive name, agent..."],
  ["/dashboard/incidents/", true, "Govern", "Incident Detail", "Jump to evidence, timeline..."],
  ["/dashboard/incidents", false, "Govern", "Incidents", "Search incident_id, dedupe_key, owner..."],
  ["/dashboard/drift/", true, "Govern", "Drift Alert", "Jump to evidence, fingerprint, traces..."],
  ["/dashboard/drift", false, "Govern", "Drift Alerts", "Search alert_id, agent, feature class..."],
  ["/dashboard/analytics", false, "Operate", "Analytics", "Jump to agent, trace, memory..."],
  ["/dashboard/billing", false, "Operate", "Billing", "Search rate card, request_id, agent..."],
  ["/dashboard/settings", false, "Operate", "Settings / Org", "Search member, token, provider..."],
  ["/dashboard/explore", false, "Investigate", "Explore", "Jump to trace, request, session, agent..."],
]

function rowMatches(pathname: string, prefix: string, exactDetail: boolean): boolean {
  if (!pathname.startsWith(prefix)) return false
  if (!exactDetail) return true
  return pathname !== prefix.slice(0, -1)
}

function metaFromRow(row: MetaRow): PageMeta {
  return { section: row[2], page: row[3], search: row[4] }
}

export function resolvePageMeta(pathname: string): PageMeta {
  for (const row of META_ROWS) {
    if (rowMatches(pathname, row[0], row[1])) return metaFromRow(row)
  }
  return DEFAULT_META
}
