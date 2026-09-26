import { OverviewWorkbench } from "@/app/dashboard/overview-workbench"
import { UnavailableDashboard } from "@/app/dashboard/unavailable-dashboard"
import { isDashboardPreviewEnabled } from "@/lib/classification"

// Preview access depends on runtime deployment flags; do not bake the decision
// into a static build artifact.
export const dynamic = "force-dynamic"

export default function DashboardPage() {
  if (!isDashboardPreviewEnabled()) {
    return <UnavailableDashboard />
  }

  return (
    <>
      <div
        role="status"
        aria-label="Preview data"
        className="border-b border-amber-500/40 bg-amber-500/10 px-4 py-2 text-center font-mono text-[11px] uppercase tracking-[0.16em] text-amber-900 dark:text-amber-200"
      >
        Preview data — no live operator contract
      </div>
      <OverviewWorkbench />
    </>
  )
}
