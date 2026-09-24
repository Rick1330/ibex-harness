import type { OnboardingProgress } from "./types"

const KEY = "ibex.onboarding.v1"

export function emptyProgress(): OnboardingProgress {
  return {
    hidden: false,
    forceOpen: false,
    agent_id: null,
    agent_slug: null,
    agent_name: null,
    pat_token_id: null,
    pat_plaintext: null,
    pat_prefix: null,
    pat_scopes: [],
    test_request_seen: false,
    invite_skipped: false,
    invites: [],
    budget_skipped: false,
    budget_visited: false,
    updated_at: new Date().toISOString(),
  }
}

export function loadProgress(orgId: string): OnboardingProgress {
  if (typeof window === "undefined") return emptyProgress()
  try {
    const raw = localStorage.getItem(`${KEY}.${orgId}`)
    if (!raw) return emptyProgress()
    return { ...emptyProgress(), ...(JSON.parse(raw) as OnboardingProgress) }
  } catch {
    return emptyProgress()
  }
}

export function saveProgress(orgId: string, p: OnboardingProgress) {
  const next = { ...p, updated_at: new Date().toISOString() }
  localStorage.setItem(`${KEY}.${orgId}`, JSON.stringify(next))
  return next
}

export function resetProgress(orgId: string) {
  const p = emptyProgress()
  saveProgress(orgId, p)
  return p
}
