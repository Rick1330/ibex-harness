import { GOVERN_NOW } from "@/lib/govern-format"

export type AccessKeyState = "active" | "overdue" | "revoked"

export type AccessKey = {
  id: string
  prefix: string
  environment: "live" | "test"
  scopes: string[]
  createdAt: string
  lastUsedAt: string | null
  createdBy: string
  rotationDueAt: string | null
  state: AccessKeyState
}

export type AccessMemberStatus = "active" | "invited"

export type AccessMember = {
  id: string
  name: string
  email: string
  role: "Viewer" | "Analyst" | "Operator" | "Admin" | "Owner"
  scope: "organization" | "production" | "staging"
  status: AccessMemberStatus
  mfaVerifiedAt: string | null
  lastActiveAt: string | null
}

export type AccessSession = {
  id: string
  actor: string
  device: string
  origin: string | null
  mfa: "verified" | "pending"
  lastSeenAt: string | null
  state: "active" | "invited"
}

export const ACCESS_KEYS: AccessKey[] = [
  {
    id: "key_9f2a",
    prefix: "ibx_live_…9f2a",
    environment: "live",
    scopes: ["runs:read", "traces:read"],
    createdAt: "2026-10-12T09:20:00Z",
    lastUsedAt: "2026-10-30T15:10:00Z",
    createdBy: "Mira Chen",
    rotationDueAt: "2026-11-17T09:20:00Z",
    state: "active",
  },
  {
    id: "key_c81e",
    prefix: "ibx_live_…c81e",
    environment: "live",
    scopes: ["memory:read", "memory:write"],
    createdAt: "2026-09-04T14:05:00Z",
    lastUsedAt: "2026-10-30T14:12:00Z",
    createdBy: "Jon Park",
    rotationDueAt: "2026-10-28T14:05:00Z",
    state: "overdue",
  },
  {
    id: "key_7b30",
    prefix: "ibx_test_…7b30",
    environment: "test",
    scopes: ["runs:read"],
    createdAt: "2026-10-20T10:40:00Z",
    lastUsedAt: "2026-10-27T15:12:00Z",
    createdBy: "Sam Ortiz",
    rotationDueAt: "2026-11-24T10:40:00Z",
    state: "active",
  },
  {
    id: "key_4c81",
    prefix: "ibx_live_…4c81",
    environment: "live",
    scopes: ["workspace:admin"],
    createdAt: "2026-07-18T11:00:00Z",
    lastUsedAt: "2026-10-25T15:12:00Z",
    createdBy: "Mira Chen",
    rotationDueAt: null,
    state: "revoked",
  },
  {
    id: "key_e920",
    prefix: "ibx_live_…e920",
    environment: "live",
    scopes: ["budgets:read", "analytics:read"],
    createdAt: "2026-08-02T08:30:00Z",
    lastUsedAt: "2026-10-30T11:12:00Z",
    createdBy: "Mira Chen",
    rotationDueAt: "2026-11-03T08:30:00Z",
    state: "active",
  },
  {
    id: "key_2d71",
    prefix: "ibx_test_…2d71",
    environment: "test",
    scopes: ["traces:read", "memory:read"],
    createdAt: "2026-10-06T16:15:00Z",
    lastUsedAt: "2026-10-22T15:12:00Z",
    createdBy: "Avery Brooks",
    rotationDueAt: "2026-11-10T16:15:00Z",
    state: "active",
  },
]

export const ACCESS_MEMBERS: AccessMember[] = [
  {
    id: "usr_mira",
    name: "Mira Chen",
    email: "mira@ws_42",
    role: "Owner",
    scope: "organization",
    status: "active",
    mfaVerifiedAt: "2026-10-30T13:12:00Z",
    lastActiveAt: "2026-10-30T15:10:00Z",
  },
  {
    id: "usr_jon",
    name: "Jon Park",
    email: "jon@ws_42",
    role: "Operator",
    scope: "production",
    status: "active",
    mfaVerifiedAt: "2026-10-30T09:12:00Z",
    lastActiveAt: "2026-10-30T15:00:00Z",
  },
  {
    id: "usr_sam",
    name: "Sam Ortiz",
    email: "sam@ws_42",
    role: "Analyst",
    scope: "production",
    status: "active",
    mfaVerifiedAt: "2026-10-30T14:27:00Z",
    lastActiveAt: "2026-10-30T14:12:00Z",
  },
  {
    id: "usr_avery",
    name: "Avery Brooks",
    email: "avery@ws_42",
    role: "Viewer",
    scope: "staging",
    status: "invited",
    mfaVerifiedAt: null,
    lastActiveAt: null,
  },
]

export const ACCESS_SESSIONS: AccessSession[] = [
  {
    id: "ses_mira",
    actor: "Mira Chen",
    device: "Chrome · macOS",
    origin: "203.0.113.42",
    mfa: "verified",
    lastSeenAt: "2026-10-30T15:10:00Z",
    state: "active",
  },
  {
    id: "ses_jon",
    actor: "Jon Park",
    device: "Firefox · Linux",
    origin: "198.51.100.17",
    mfa: "verified",
    lastSeenAt: "2026-10-30T15:00:00Z",
    state: "active",
  },
  {
    id: "ses_sam",
    actor: "Sam Ortiz",
    device: "Safari · iOS",
    origin: "192.0.2.88",
    mfa: "verified",
    lastSeenAt: "2026-10-30T14:12:00Z",
    state: "active",
  },
  {
    id: "ses_avery",
    actor: "Avery Brooks",
    device: "Chrome · Windows",
    origin: null,
    mfa: "pending",
    lastSeenAt: null,
    state: "invited",
  },
]

export const ACCESS_ROLES = ["Viewer", "Analyst", "Operator", "Admin"] as const
export const ACCESS_CAPABILITIES = [
  "Read metadata",
  "Read content",
  "Investigate",
  "Export",
  "Govern",
  "Mutate",
  "Administer",
] as const

export const ACCESS_MATRIX: boolean[][] = [
  [true, false, false, false, false, false, false],
  [true, true, true, false, false, false, false],
  [true, true, true, true, true, false, false],
  [true, true, true, true, true, true, true],
]

export function accessKeyRotationLabel(key: AccessKey): string {
  if (key.state === "revoked") return "revoked"
  if (key.state === "overdue") return "overdue"
  if (!key.rotationDueAt) return "—"
  const days = Math.max(0, Math.ceil((Date.parse(key.rotationDueAt) - GOVERN_NOW) / 86_400_000))
  return `in ${days}d`
}

export function accessCounts() {
  return {
    activeKeys: ACCESS_KEYS.filter((key) => key.state === "active").length,
    liveKeys: ACCESS_KEYS.filter((key) => key.environment === "live" && key.state !== "revoked").length,
    testKeys: ACCESS_KEYS.filter((key) => key.environment === "test" && key.state !== "revoked").length,
    overdueKeys: ACCESS_KEYS.filter((key) => key.state === "overdue").length,
    revokedKeys: ACCESS_KEYS.filter((key) => key.state === "revoked").length,
    members: ACCESS_MEMBERS.length,
    pendingInvites: ACCESS_MEMBERS.filter((member) => member.status === "invited").length,
    activeSessions: ACCESS_SESSIONS.filter((session) => session.state === "active").length,
    pendingMfa: ACCESS_SESSIONS.filter((session) => session.mfa === "pending").length,
  }
}
