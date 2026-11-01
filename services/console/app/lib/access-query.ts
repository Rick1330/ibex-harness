export const ACCESS_TABS = ["keys", "members", "sessions", "roles"] as const
export type AccessTab = (typeof ACCESS_TABS)[number]

export const ACCESS_KEY_STATES = ["all", "active", "overdue", "revoked"] as const
export type AccessKeyStateFilter = (typeof ACCESS_KEY_STATES)[number]

export const ACCESS_MEMBER_STATES = ["all", "active", "invited"] as const
export type AccessMemberStateFilter = (typeof ACCESS_MEMBER_STATES)[number]

export type AccessState = {
  tab: AccessTab
  q: string
  keyState: AccessKeyStateFilter
  memberState: AccessMemberStateFilter
  item: string
}

export const ACCESS_DEFAULT: AccessState = {
  tab: "keys",
  q: "",
  keyState: "all",
  memberState: "all",
  item: "",
}

function one(value: unknown): string {
  if (Array.isArray(value)) return typeof value[0] === "string" ? value[0] : ""
  return typeof value === "string" ? value : ""
}

function includes<T extends readonly string[]>(values: T, value: string, fallback: T[number]): T[number] {
  return (values as readonly string[]).includes(value) ? (value as T[number]) : fallback
}

export function parseAccessQuery(query: Record<string, unknown>): AccessState {
  return {
    tab: includes(ACCESS_TABS, one(query.tab), ACCESS_DEFAULT.tab),
    q: one(query.q).slice(0, 120),
    keyState: includes(ACCESS_KEY_STATES, one(query.keyState), ACCESS_DEFAULT.keyState),
    memberState: includes(ACCESS_MEMBER_STATES, one(query.memberState), ACCESS_DEFAULT.memberState),
    item: one(query.item).slice(0, 120),
  }
}

export function serializeAccessQuery(state: AccessState): URLSearchParams {
  const params = new URLSearchParams()
  if (state.tab !== ACCESS_DEFAULT.tab) params.set("tab", state.tab)
  if (state.q.trim()) params.set("q", state.q.trim())
  if (state.keyState !== ACCESS_DEFAULT.keyState) params.set("keyState", state.keyState)
  if (state.memberState !== ACCESS_DEFAULT.memberState) params.set("memberState", state.memberState)
  if (state.item) params.set("item", state.item)
  return params
}

export function accessHref(state: AccessState): string {
  const query = serializeAccessQuery(state).toString()
  return query ? `/access?${query}` : "/access"
}
