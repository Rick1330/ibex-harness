import { OverviewWorkbench } from "@/app/dashboard/overview-workbench"
import { LiveOverview } from "@/app/dashboard/live-overview"
import { UnavailableDashboard } from "@/app/dashboard/unavailable-dashboard"
import {
  isDashboardPreviewEnabled,
  isLiveD1Enabled,
} from "@/lib/classification"

// Preview access depends on runtime deployment flags; do not bake the decision
// into a static build artifact.
export const dynamic = "force-dynamic"

export default function DashboardPage() {
  if (isLiveD1Enabled()) return <LiveOverview />
  if (!isDashboardPreviewEnabled()) {
    return <UnavailableDashboard />
  }

  return (
    <OverviewWorkbench />
  )
}
