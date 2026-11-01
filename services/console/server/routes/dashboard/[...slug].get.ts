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

export default defineEventHandler((event) => {
  const url = getRequestURL(event)
  const segments = url.pathname.split("/").filter(Boolean)
  const rest = segments.slice(1)
  const first = rest[0]

  let target: string | null = null
  if (!first || first === "overview") {
    target = "/"
  } else if (first === "explore") {
    target = `/explore${rest.length > 1 ? `/${rest.slice(1).join("/")}` : ""}`
  } else if (first && DIRECT_REDIRECTS[first]) {
    target = DIRECT_REDIRECTS[first]!
  }

  if (!target) {
    throw createError({ statusCode: 404, statusMessage: "Not found" })
  }

  return sendRedirect(event, `${target}${url.search}`, 308)
})
