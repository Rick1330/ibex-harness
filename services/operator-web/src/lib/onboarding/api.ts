/**
 * Onboarding fixture RPCs — createAgent (POST /v1/agents), PAT issue,
 * create_user_invite, first-trace poll.
 */

import { createAgent } from "@/lib/agents/api"
import type { AgentDetail } from "@/lib/agents/types"
import { PERMISSION_PICKER } from "@/lib/settings/fixtures"
import type { MemberRole, OnboardingInvite } from "./types"

function delay(ms = 280) {
  return new Promise((r) => window.setTimeout(r, ms))
}

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

export function slugifyAgentName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64)
}

export function validateAgentSlug(slug: string): string | null {
  if (!slug) return "Slug is required"
  if (!SLUG_RE.test(slug)) {
    return "Slug must match ^[a-z0-9-]+$ (agents_slug_format)"
  }
  return null
}

export async function onboardingCreateAgent(input: {
  name: string
  slug: string
  tags?: string[]
  orgId: string
}): Promise<AgentDetail> {
  const err = validateAgentSlug(input.slug)
  if (err) throw new Error(err)
  return createAgent({
    name: input.name.trim(),
    slug: input.slug.trim(),
    tags: input.tags ?? [],
    org_id: input.orgId,
  })
}

export type IssuedPat = {
  token_id: string
  prefix: string
  plaintext: string
  scopes: string[]
  agent_id: string | null
}

/** Issue PAT — secret shown once; mirrors Settings token create. */
export async function issueOnboardingPat(input: {
  name: string
  scopes: string[]
  agent_id: string | null
}): Promise<IssuedPat> {
  await delay(320)
  if (input.scopes.length === 0) {
    throw new Error("Select at least one permission bit")
  }
  for (const wire of input.scopes) {
    if (!PERMISSION_PICKER.some((p) => p.wire === wire)) {
      throw new Error(`Unknown permission: ${wire}`)
    }
  }
  const uuid = crypto.randomUUID().replace(/-/g, "")
  const secret =
    crypto.randomUUID().replace(/-/g, "") + crypto.randomUUID().replace(/-/g, "")
  const plaintext = `ibex_pat_${uuid}_${secret}`
  return {
    token_id: `tok_${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`,
    prefix: plaintext.slice(0, 18) + "…",
    plaintext,
    scopes: input.scopes,
    agent_id: input.agent_id,
  }
}

export async function createUserInvite(input: {
  email: string
  name: string
  role: MemberRole
}): Promise<OnboardingInvite> {
  await delay(300)
  const email = input.email.trim().toLowerCase()
  if (!email.includes("@")) throw new Error("Enter a valid email")
  if (!input.name.trim()) throw new Error("Name is required")
  const roles: MemberRole[] = ["owner", "admin", "member", "viewer"]
  if (!roles.includes(input.role)) throw new Error("Invalid role")
  return {
    user_id: `usr_${crypto.randomUUID().replace(/-/g, "").slice(0, 6)}`,
    email,
    name: input.name.trim(),
    role: input.role,
    status: "invited",
    invited_at: new Date().toISOString(),
  }
}

/**
 * Poll for first Explore row — fixture completes after operator confirms
 * or after simulateFirstTrace(). Real: 4.D.2 list traces.
 */
let firstTraceAt: number | null = null

export function simulateFirstTrace() {
  firstTraceAt = Date.now()
}

export function clearFirstTraceSim() {
  firstTraceAt = null
}

export async function pollFirstTrace(opts?: {
  sinceMs?: number
}): Promise<{ found: boolean }> {
  await delay(400)
  if (firstTraceAt && Date.now() - firstTraceAt < (opts?.sinceMs ?? 600_000)) {
    return { found: true }
  }
  return { found: false }
}

export function buildTestCurl(opts: {
  baseUrl: string
  token: string | null
  agentId: string | null
  masked?: boolean
}): string {
  const token = opts.token
    ? opts.masked
      ? `${opts.token.slice(0, 18)}…`
      : opts.token
    : "ibex_pat_<uuid>_<secret>"
  const agent = opts.agentId ?? "<agent_id>"
  return `curl -sS -X POST '${opts.baseUrl}/v1/chat/completions' \\
  -H 'Authorization: Bearer ${token}' \\
  -H 'X-IBEX-Agent-ID: ${agent}' \\
  -H 'Content-Type: application/json' \\
  -d '{"model":"gpt-4-turbo","messages":[{"role":"user","content":"ping"}]}'`
}

export function proxyBaseUrl(): string {
  if (typeof window === "undefined") return "https://api.ibex.local"
  return (
    process.env.NEXT_PUBLIC_IBEX_API_BASE ??
    `${window.location.origin.replace(/:\d+$/, ":8080")}`
  )
}
