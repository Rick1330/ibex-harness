"use client"

import { EmptyState, EmptyStateButton } from "@/components/list/empty-state"
import { useOnboardingOptional } from "@/components/onboarding/onboarding-provider"
import { PAGE_EMPTY, type OnboardingStepId } from "@/lib/onboarding/types"

/** Shared per-page empty — routes CTAs back into the Overview checklist. */
export function PageEmptyState({
  page,
  actionLabel,
  onAction,
}: {
  page: keyof typeof PAGE_EMPTY
  actionLabel?: string
  onAction?: () => void
}) {
  const copy = PAGE_EMPTY[page]
  const onboarding = useOnboardingOptional()

  const go = () => {
    if (onAction) {
      onAction()
      return
    }
    if (copy.step && onboarding) {
      onboarding.openChecklist()
      onboarding.setActiveStep(copy.step as OnboardingStepId)
    }
    window.location.href = copy.href ?? "/dashboard#onboarding"
  }

  const showCta = Boolean(copy.step || copy.href || onAction)

  return (
    <EmptyState
      title={copy.title}
      description={copy.description}
      action={
        showCta ? (
          <EmptyStateButton
            onClick={go}
            variant={copy.step ? "default" : "outline"}
          >
            {actionLabel ??
              (copy.step === "create_agent"
                ? "Create agent"
                : copy.step === "set_budget"
                  ? "Set a budget"
                  : copy.step
                    ? "Open setup guide"
                    : "Continue")}
          </EmptyStateButton>
        ) : undefined
      }
    />
  )
}
