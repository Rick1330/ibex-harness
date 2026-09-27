import { LiveExplorePage } from "@/app/dashboard/explore/live-page"
import PreviewExplorePage from "@/app/dashboard/explore/preview-page"
import { isDashboardPreviewEnabled, isLiveD1Enabled } from "@/lib/classification"

export const dynamic = "force-dynamic"

export default function ExplorePage() {
  if (isLiveD1Enabled()) return <LiveExplorePage />
  if (isDashboardPreviewEnabled()) return <PreviewExplorePage />
  return null
}
