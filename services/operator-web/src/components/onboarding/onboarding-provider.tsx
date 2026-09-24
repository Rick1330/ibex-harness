"use client"

import * as React from "react"

import { useAuth } from "@/components/auth/auth-provider"
import { countOrgAgents } from "@/lib/agents/api"
import { clearFirstTraceSim } from "@/lib/onboarding/api"
import {
  emptyProgress,
  loadProgress,
  saveProgress,
} from "@/lib/onboarding/store"
import type {
  OnboardingProgress,
  OnboardingStepId,
} from "@/lib/onboarding/types"
import { ONBOARDING_STEPS } from "@/lib/onboarding/types"

type OnboardingContextValue = {
  ready: boolean
  orgId: string
  agentCount: number
  progress: OnboardingProgress
  setProgress: (
    p: OnboardingProgress | ((prev: OnboardingProgress) => OnboardingProgress),
  ) => void
  requiredComplete: boolean
  allDone: boolean
  showChecklist: boolean
  showSetupGuide: boolean
  activeStep: OnboardingStepId | null
  setActiveStep: (s: OnboardingStepId | null) => void
  hideChecklist: () => void
  openChecklist: () => void
  refreshAgentCount: () => Promise<void>
  isStepDone: (id: OnboardingStepId) => boolean
  demoZeroAgents: boolean
  setDemoZeroAgents: (v: boolean) => void
  resetOnboarding: () => void
}

const OnboardingContext = React.createContext<OnboardingContextValue | null>(
  null,
)

export function useOnboarding() {
  const ctx = React.useContext(OnboardingContext)
  if (!ctx) {
    throw new Error("useOnboarding must be used within OnboardingProvider")
  }
  return ctx
}

export function useOnboardingOptional() {
  return React.useContext(OnboardingContext)
}

function isDone(
  p: OnboardingProgress,
  id: OnboardingStepId,
  agentCount: number,
) {
  switch (id) {
    case "create_agent":
      return Boolean(p.agent_id) || agentCount > 0
    case "issue_pat":
      return Boolean(p.pat_token_id)
    case "test_request":
      return p.test_request_seen
    case "invite_teammate":
      return p.invite_skipped || p.invites.length > 0
    case "set_budget":
      return p.budget_skipped || p.budget_visited
  }
}

export function OnboardingProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const { session, ready: authReady } = useAuth()
  const orgId = session?.org_id ?? "org_acme"
  const [ready, setReady] = React.useState(false)
  const [progress, setProgressState] =
    React.useState<OnboardingProgress>(emptyProgress)
  const [agentCount, setAgentCount] = React.useState(0)
  const [activeStep, setActiveStep] = React.useState<OnboardingStepId | null>(
    null,
  )
  const [demoZeroAgents, setDemoZeroAgentsState] = React.useState(false)

  const refreshAgentCount = React.useCallback(async () => {
    if (demoZeroAgents) {
      setAgentCount(0)
      return
    }
    const n = await countOrgAgents(orgId)
    setAgentCount(n)
  }, [orgId, demoZeroAgents])

  React.useEffect(() => {
    if (!authReady || !session) return
    setProgressState(loadProgress(orgId))
    void refreshAgentCount().finally(() => setReady(true))
  }, [authReady, session, orgId, refreshAgentCount])

  React.useEffect(() => {
    if (demoZeroAgents) setAgentCount(0)
    else void refreshAgentCount()
  }, [demoZeroAgents, refreshAgentCount])

  const setProgress = React.useCallback(
    (
      next:
        OnboardingProgress | ((prev: OnboardingProgress) => OnboardingProgress),
    ) => {
      setProgressState((prev) => {
        const value = typeof next === "function" ? next(prev) : next
        return saveProgress(orgId, value)
      })
    },
    [orgId],
  )

  const effectiveCount = demoZeroAgents ? 0 : agentCount

  const isStepDone = React.useCallback(
    (id: OnboardingStepId) => isDone(progress, id, effectiveCount),
    [progress, effectiveCount],
  )

  const requiredComplete = ONBOARDING_STEPS.filter((s) => !s.optional).every(
    (s) => isStepDone(s.id),
  )
  const allDone = ONBOARDING_STEPS.every((s) => isStepDone(s.id))

  const showChecklist =
    ready &&
    (progress.forceOpen ||
      ((effectiveCount === 0 || !requiredComplete) && !progress.hidden))

  const hideChecklist = () =>
    setProgress((p) => ({ ...p, hidden: true, forceOpen: false }))
  const openChecklist = () => {
    setProgress((p) => ({ ...p, hidden: false, forceOpen: true }))
    setActiveStep(null)
  }

  const setDemoZeroAgents = (v: boolean) => {
    setDemoZeroAgentsState(v)
    if (v) {
      clearFirstTraceSim()
      setProgress({
        ...emptyProgress(),
        forceOpen: true,
        hidden: false,
      })
      setActiveStep("create_agent")
    }
  }

  const resetOnboarding = () => {
    clearFirstTraceSim()
    setDemoZeroAgentsState(true)
    setProgress({
      ...emptyProgress(),
      forceOpen: true,
      hidden: false,
    })
    setActiveStep("create_agent")
  }

  return (
    <OnboardingContext.Provider
      value={{
        ready,
        orgId,
        agentCount: effectiveCount,
        progress,
        setProgress,
        requiredComplete,
        allDone,
        showChecklist,
        showSetupGuide: ready,
        activeStep,
        setActiveStep,
        hideChecklist,
        openChecklist,
        refreshAgentCount,
        isStepDone,
        demoZeroAgents,
        setDemoZeroAgents,
        resetOnboarding,
      }}
    >
      {children}
    </OnboardingContext.Provider>
  )
}
