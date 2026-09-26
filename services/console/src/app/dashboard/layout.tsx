// The preview gate depends on runtime deployment flags; never bake its result
// into a static redirect during `next build`.
export const dynamic = "force-dynamic"

/**
 * The transplanted route tree is presentation-only until tenant-scoped APIs are
 * connected. Keep fixture imports out of production execution by gating the
 * entire dashboard subtree on the explicit, server-validated preview pair.
 */
import { UnavailableDashboard } from "@/app/dashboard/unavailable-dashboard"
import {
  isDashboardPreviewEnabled,
  isLiveD1Enabled,
} from "@/lib/classification"

export default function DashboardLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  if (!isDashboardPreviewEnabled() && !isLiveD1Enabled()) {
    return <UnavailableDashboard />
  }

  return children
}
