import { getRequestURL, sendRedirect } from "h3"

const DIRECT_REDIRECTS: Record<string, string> = {
  platform: "/platform",
  agents: "/agents",
  sessions: "/sessions",
  memories: "/memories",
  directives: "/directives",
  incidents: "/incidents",
  drift: "/drift",
  analytics: "/analytics",
  settings: "/settings",
  evidence: "/evidence",
  policies: "/policies",
  audit: "/audit",
  "audit-log": "/audit",
  budgets: "/budgets",
  billing: "/budgets",
  providers: "/providers",
  "mcp-tools": "/mcp-tools",
  access: "/access",
}

/** Legacy roots that have a real detail route at the same suffix. */
const DETAIL_ROOTS = new Set(["agents", "sessions", "memories", "directives", "policies", "drift", "audit"])

export default defineEventHandler((event) => {
  const url = getRequestURL(event)
  const segments = url.pathname.split("/").filter(Boolean)
  const rest = segments.slice(1)
  const first = rest[0]
  const suffix = rest.slice(1).join("/")

  let target: string | null = null
  if (!first || first === "overview") {
    target = suffix ? null : "/"
  } else if (first === "explore") {
    target = `/explore${suffix ? `/${suffix}` : ""}`
  } else if (first && DIRECT_REDIRECTS[first]) {
    const base = DIRECT_REDIRECTS[first]!
    if (!suffix) {
      target = base
    } else if (DETAIL_ROOTS.has(first)) {
      target = `${base}/${suffix}`
    }
  }

  if (!target) {
    throw createError({ statusCode: 404, statusMessage: "Not found" })
  }

  return sendRedirect(event, `${target}${url.search}`, 308)
})
