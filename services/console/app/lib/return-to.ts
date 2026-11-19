// Explore is reachable from a session turn (trace link) and from a memory
// (provenance link), so its back target may be a session or memory record as
// well as an Explore list. Anything else is not a return target.
const RECORD_RETURN =
  /^\/(sessions|memories)\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:\?[^#]*)?$/i

export function safeExploreReturn(value: unknown): string {
  if (typeof value !== "string") return "/explore"
  if (value.startsWith("//")) return "/explore"
  if (value.startsWith("/explore") || RECORD_RETURN.test(value)) return value
  return "/explore"
}

export function safeMemoryReturn(value: unknown): string {
  if (typeof value !== "string") return "/memories"
  if (value.startsWith("//")) return "/memories"
  if (value.startsWith("/sessions/")) return value
  if (!value.startsWith("/memories")) return "/memories"
  if (value.startsWith("/memories/")) return "/memories"
  return value
}

export function safeSessionReturn(value: unknown): string {
  if (typeof value !== "string") return "/sessions"
  if (!value.startsWith("/sessions")) return "/sessions"
  if (value.startsWith("//")) return "/sessions"
  if (value.startsWith("/sessions/")) return "/sessions"
  return value
}

// A session row links to its agent, so an agent page opened from the Sessions
// list must be able to return there. Only the list shape is admitted: exactly
// `/sessions`, optionally with a query. The record shape (`/sessions/<id>`) is a
// different page and is not a target of this link, and a fragment is rejected
// because the back link would land below the heading.
const SESSIONS_LIST_RETURN = /^\/sessions(?:\?[^#]*)?$/

export function safeAgentReturn(value: unknown): string {
  if (typeof value !== "string") return "/agents"
  if (value.startsWith("//")) return "/agents"
  if (SESSIONS_LIST_RETURN.test(value)) return value
  if (!value.startsWith("/agents")) return "/agents"
  if (value.startsWith("/agents/")) return "/agents"
  return value
}

/**
 * The back-link label for a sanitised agent return target. The label follows the
 * destination, so a reader is never told "Back to agents" while the link goes to
 * the Sessions list.
 */
export function agentReturnLabel(href: string): string {
  return href.startsWith("/sessions") ? "Back to sessions" : "Back to agents"
}

export function safeDirectiveReturn(value: unknown): string {
  if (typeof value !== "string") return "/directives"
  if (value.startsWith("//")) return "/directives"
  if (!value.startsWith("/directives")) return "/directives"
  if (value.startsWith("/directives/")) return "/directives"
  return value
}

export function safePolicyReturn(value: unknown): string {
  if (typeof value !== "string") return "/policies"
  if (value.startsWith("//")) return "/policies"
  if (!value.startsWith("/policies")) return "/policies"
  if (value.startsWith("/policies/")) return "/policies"
  return value
}
