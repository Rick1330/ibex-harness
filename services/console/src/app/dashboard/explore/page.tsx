import { LiveExplorePage } from "@/app/dashboard/explore/live-page"
import PreviewExplorePage from "@/app/dashboard/explore/preview-page"
import { isDashboardPreviewEnabled, isLiveD1Enabled } from "@/lib/classification"

export const dynamic = "force-dynamic"

export default async function ExplorePage({
  searchParams,
}: Readonly<{
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}>) {
  if (isLiveD1Enabled()) return <LiveExplorePage searchParams={searchParams} />
  if (isDashboardPreviewEnabled()) return <PreviewExplorePage />
  return null
}
