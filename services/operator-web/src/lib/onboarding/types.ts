/**
 * First-run onboarding — derived from zero agents + checklist progress.
 * No has_completed_onboarding column; progress lives in org settings-shaped
 * local store (≤50 keys / ≤8KB spirit of test_organization_settings_bounds).
 */

export type OnboardingStepId =
  | "create_agent"
  | "issue_pat"
  | "test_request"
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
  pat_token_id: string | null
  /** Plaintext shown once — cleared after dismiss; masked in curl thereafter. */
  pat_plaintext: string | null
  pat_prefix: string | null
  pat_scopes: string[]
  test_request_seen: boolean
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
  {
    id: "issue_pat",
    label: "Issue a Personal Access Token (PAT)",
    optional: false,
  },
  {
    id: "test_request",
    label: "Send a test request through the proxy",
    optional: false,
  },
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
      "Send a test request through the proxy to populate overview metrics.",
    step: "test_request",
  },
  explore: {
    title: "No traces recorded",
    description:
      "Traces appear once a protected proxy call lands with a valid PAT and agent header.",
    step: "test_request",
  },
  sessions: {
    title: "No sessions yet",
    description:
      "Memories populate once your agent runs. Send a test request to open the first session.",
    step: "test_request",
  },
  memories: {
    title: "No sessions yet — memories populate once your agent runs",
    description:
      "Extraction runs after live traffic. Complete the test-request step to seed the first session.",
    step: "test_request",
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
      "Send traffic now; period rollups appear once the billing window ends. Or jump to the test-request step.",
    step: "test_request",
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
