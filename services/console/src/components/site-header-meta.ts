export type PageMeta = { section: string; page: string; search: string }

const pageMeta: Record<
  string,
  { section: string; page: string; search: string }
> = {
  "/dashboard": {
    section: "Overview",
    page: "Overview",
    search: "Search metrics, agents, sessions...",
  },
  "/dashboard/explore": {
    section: "Investigate",
    page: "Explore",
    search: "Jump to trace, request, session, agent...",
  },
}

export function resolvePageMeta(pathname: string): PageMeta {
  if (pathname.startsWith("/dashboard/explore/t/")) {
    return {
      section: "Investigate",
      page: "Trace Inspector",
      search: "Jump to span, memory, request...",
    }
  }
  if (
    pathname.startsWith("/dashboard/agents/") &&
    pathname !== "/dashboard/agents"
  ) {
    return {
      section: "Investigate",
      page: "Agent Detail",
      search: "Jump to sessions, directive...",
    }
  }
  if (pathname.startsWith("/dashboard/agents")) {
    return {
      section: "Investigate",
      page: "Agents",
      search: "Search agent name, directive...",
    }
  }
  if (
    pathname.startsWith("/dashboard/sessions/") &&
    pathname !== "/dashboard/sessions"
  ) {
    return {
      section: "Investigate",
      page: "Session Timeline",
      search: "Jump to turn, memory, checkpoint...",
    }
  }
  if (pathname.startsWith("/dashboard/sessions")) {
    return {
      section: "Investigate",
      page: "Sessions",
      search: "Search session_id, agent, tag...",
    }
  }
  if (
    pathname.startsWith("/dashboard/memories/") &&
    pathname !== "/dashboard/memories"
  ) {
    return {
      section: "Investigate",
      page: "Memory Detail",
      search: "Jump to lineage, session...",
    }
  }
  if (pathname.startsWith("/dashboard/memories")) {
    return {
      section: "Investigate",
      page: "Memories",
      search: "Search memory_id, category...",
    }
  }
  if (
    pathname.startsWith("/dashboard/directives/") &&
    pathname !== "/dashboard/directives"
  ) {
    return {
      section: "Govern",
      page: "Directive Detail",
      search: "Jump to version, scenario, ledger...",
    }
  }
  if (pathname.startsWith("/dashboard/directives")) {
    return {
      section: "Govern",
      page: "Directives",
      search: "Search directive name, agent...",
    }
  }
  if (
    pathname.startsWith("/dashboard/incidents/") &&
    pathname !== "/dashboard/incidents"
  ) {
    return {
      section: "Govern",
      page: "Incident Detail",
      search: "Jump to evidence, timeline...",
    }
  }
  if (pathname.startsWith("/dashboard/incidents")) {
    return {
      section: "Govern",
      page: "Incidents",
      search: "Search incident_id, dedupe_key, owner...",
    }
  }
  if (
    pathname.startsWith("/dashboard/drift/") &&
    pathname !== "/dashboard/drift"
  ) {
    return {
      section: "Govern",
      page: "Drift Alert",
      search: "Jump to evidence, fingerprint, traces...",
    }
  }
  if (pathname.startsWith("/dashboard/drift")) {
    return {
      section: "Govern",
      page: "Drift Alerts",
      search: "Search alert_id, agent, feature class...",
    }
  }
  if (pathname.startsWith("/dashboard/analytics")) {
    return {
      section: "Operate",
      page: "Analytics",
      search: "Jump to agent, trace, memory...",
    }
  }
  if (pathname.startsWith("/dashboard/billing")) {
    return {
      section: "Operate",
      page: "Billing",
      search: "Search rate card, request_id, agent...",
    }
  }
  if (pathname.startsWith("/dashboard/settings")) {
    return {
      section: "Operate",
      page: "Settings / Org",
      search: "Search member, token, provider...",
    }
  }
  if (pathname.startsWith("/dashboard/explore")) {
    return pageMeta["/dashboard/explore"]
  }
  if (pathname === "/dashboard") {
    return pageMeta["/dashboard"]
  }
  return pageMeta["/dashboard"]
}


