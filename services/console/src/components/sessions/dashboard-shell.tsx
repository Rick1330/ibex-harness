"use client"

import * as React from "react"
import { usePathname } from "next/navigation"

import { AppSidebar } from "@/components/app-sidebar"
import { AuthProvider, useAuth } from "@/components/auth/auth-provider"
import { StepUpModal } from "@/components/auth/step-up-modal"
import { OnboardingProvider } from "@/components/onboarding/onboarding-provider"
import { SiteHeader } from "@/components/site-header"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"
import { FRESHNESS_TONE } from "@/lib/shell-health"
import type { OperatorContext, PlatformHealth } from "@/lib/api/contracts"
import { cn } from "@/lib/utils"

/** Shared dashboard chrome — auth gate + session refresh + step-up modal. */
export type DashboardShellProps = {
  children: React.ReactNode
  liveMode?: boolean
  showPreviewBanner?: boolean
  operatorContext?: OperatorContext | null
  platformHealth?: PlatformHealth | null
}

function SessionBoundOnboarding({
  liveMode,
  children,
}: {
  liveMode: boolean
  children: React.ReactNode
}) {
  return liveMode ? children : <OnboardingProvider>{children}</OnboardingProvider>
}

export function DashboardShell({
  children,
  liveMode = false,
  showPreviewBanner = true,
  operatorContext = null,
  platformHealth = null,
}: DashboardShellProps) {
  return (
    <AuthProvider>
      <DashboardShellInner
        liveMode={liveMode}
        showPreviewBanner={showPreviewBanner}
        operatorContext={operatorContext}
        platformHealth={platformHealth}
      >
        {children}
      </DashboardShellInner>
    </AuthProvider>
  )
}

function DashboardShellInner({
  children,
  liveMode = false,
  showPreviewBanner = true,
  operatorContext = null,
  platformHealth = null,
}: DashboardShellProps) {
  const { ready, session, banner, tryRefresh, logout } = useAuth()
  const pathname = usePathname()

  // Silent refresh probe — simulates 401 → refresh → retry path.
  React.useEffect(() => {
    if (!session) return
    const id = window.setInterval(() => {
      void tryRefresh()
    }, 120_000)
    return () => window.clearInterval(id)
  }, [session, tryRefresh])

  if (!ready) {
    return (
      <div className="flex min-h-svh items-center justify-center p-6">
        <Skeleton className="h-8 w-48" />
      </div>
    )
  }

  if (session?.mfa_required && !session.totp_enrolled) {
    return (
      <div className="flex min-h-svh items-center justify-center p-6">
        <Skeleton className="h-8 w-48" />
      </div>
    )
  }

  return (
    <SessionBoundOnboarding liveMode={liveMode}>
      <SidebarProvider
        style={
          {
            "--sidebar-width": "calc(var(--spacing) * 72)",
            "--header-height": "calc(var(--spacing) * 12)",
          } as React.CSSProperties
        }
      >
        <AppSidebar
          variant="inset"
          liveMode={liveMode}
          operatorContext={operatorContext}
        />
        <SidebarInset>
          <SiteHeader
            liveMode={liveMode}
            operatorContext={operatorContext}
            platformHealth={platformHealth}
          />
          {showPreviewBanner ? (
            <div
              role="status"
              aria-label="Preview data"
              className="border-b border-amber-500/40 bg-amber-500/10 px-4 py-2 text-center font-mono text-[11px] uppercase tracking-[0.16em] text-amber-900 dark:text-amber-200"
            >
              Preview data — no live operator contract
            </div>
          ) : null}
          {banner ? (
            <div
              className={cn(
                "border-b px-4 py-2 text-[12px]",
                banner.kind === "degraded" &&
                  "border-amber-500/40 bg-amber-500/5 text-foreground",
                banner.kind === "stale" &&
                  "border-destructive/40 bg-destructive/5 text-foreground",
              )}
            >
              <span
                className={cn(
                  "mr-2 inline-block size-1.5 rounded-full",
                  FRESHNESS_TONE[banner.kind].dot,
                )}
              />
              {banner.message}
              <button
                type="button"
                className="ml-3 underline-offset-2 hover:underline"
                onClick={() => void tryRefresh()}
              >
                Retry refresh
              </button>
              <button
                type="button"
                className="ml-2 text-muted-foreground underline-offset-2 hover:underline"
                onClick={() => logout()}
              >
                Sign out
              </button>
            </div>
          ) : null}
          <div className="flex flex-1 flex-col" data-pathname={pathname}>
            {children}
          </div>
        </SidebarInset>
        <StepUpModal />
      </SidebarProvider>
    </SessionBoundOnboarding>
  )
}

export const pagePad =
  "mx-auto flex w-full max-w-[1440px] flex-col gap-3 px-3 py-3 sm:px-4 sm:py-4 md:py-5 lg:px-6"

/** Shared dashboard panel surface — readable in light + dark. */
export const panelClass =
  "h-fit min-w-0 gap-0 rounded-lg border border-border bg-card py-0 shadow-[0_1px_2px_oklch(0_0_0/0.06)] dark:shadow-none"

/** Nested inset blocks (tables, filter chips, sub-panels). */
export const insetClass =
  "min-w-0 rounded-lg border border-border bg-card shadow-[0_1px_2px_oklch(0_0_0/0.04)] dark:shadow-none"
