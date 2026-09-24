/**
 * First-run onboarding — derived from zero agents + checklist progress.
 * No has_completed_onboarding column; progress lives in org settings-shaped
 * local store (≤50 keys / ≤8KB spirit of test_organization_settings_bounds).
 */

export type OnboardingStepId =
  | "create_agent"
  | "invite_teammate"
  | "set_budget"

export type MemberRole = "owner" | "admin" | "member" | "viewer"

export type OnboardingInvite = {
  user_id: string
  email: string
  name: string
  role: MemberRole
  status: "invited"
  invited_at: string
}

export type OnboardingProgress = {
  /** Checklist card hidden on Overview — reopen via sidebar Setup guide. */
  hidden: boolean
  /** Operator explicitly reopened after completion / hide. */
  forceOpen: boolean
  agent_id: string | null
  agent_slug: string | null
  agent_name: string | null
  invite_skipped: boolean
  invites: OnboardingInvite[]
  budget_skipped: boolean
  budget_visited: boolean
  updated_at: string
}

export const ONBOARDING_STEPS: {
  id: OnboardingStepId
  label: string
  optional: boolean
}[] = [
  { id: "create_agent", label: "Create your first agent", optional: false },
  { id: "invite_teammate", label: "Invite a teammate", optional: true },
  {
    id: "set_budget",
    label: "Set a budget (recommended before production)",
    optional: true,
  },
]

export const PAGE_EMPTY: Record<
  string,
  { title: string; description: string; step?: OnboardingStepId; href?: string }
> = {
  overview: {
    title: "No traffic yet",
    description:
      "Connect the authenticated proxy contract to populate overview metrics.",
  },
  explore: {
    title: "No traces recorded",
    description:
      "Traces appear once the authenticated proxy contract is connected.",
  },
  sessions: {
    title: "No sessions yet",
    description:
      "Memories populate once the authenticated agent contract is connected.",
  },
  memories: {
    title: "No sessions yet — memories populate once your agent runs",
    description:
      "Extraction runs after the authenticated traffic contract is connected.",
  },
  directives: {
    title: "No directive versions — every agent needs at least one",
    description:
      "Create a directive version for your agent before promoting production traffic.",
    href: "/dashboard/directives",
  },
  drift: {
    title: "Drift detection needs 7+ days of baseline traffic",
    description:
      "This is a statistical requirement, not a missing feature. Alerts stay empty until a stable baseline exists.",
  },
  analytics: {
    title: "Analytics populate after your first billing period closes",
    description:
      "Period rollups appear once the authenticated traffic contract is connected.",
  },
  billing: {
    title: "No usage recorded",
    description:
      "Usage accrues from proxy traffic. Set a budget before production so a runaway agent cannot overspend.",
    step: "set_budget",
  },
  agents: {
    title: "No agents yet",
    description:
      "Create your first agent to start routing traffic through IBEX Harness.",
    step: "create_agent",
  },
}
