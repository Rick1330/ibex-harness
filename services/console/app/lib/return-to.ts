export function safeExploreReturn(value: unknown): string {
  if (typeof value !== "string") return "/explore"
  if (!value.startsWith("/explore")) return "/explore"
  if (value.startsWith("//")) return "/explore"
  return value
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

export function safeAgentReturn(value: unknown): string {
  if (typeof value !== "string") return "/agents"
  if (value.startsWith("//")) return "/agents"
  if (!value.startsWith("/agents")) return "/agents"
  if (value.startsWith("/agents/")) return "/agents"
  return value
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
