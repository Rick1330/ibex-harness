import { LiveTracePage } from "@/app/dashboard/explore/t/[traceId]/live-page"
import PreviewTraceInspectorPage from "@/app/dashboard/explore/t/[traceId]/preview-page"
import { isDashboardPreviewEnabled, isLiveD1Enabled } from "@/lib/classification"

export const dynamic = "force-dynamic"

export default async function TraceInspectorPage({ params }: Readonly<{ params: Promise<{ traceId: string }> }>) {
  const { traceId } = await params
  if (isLiveD1Enabled()) return <LiveTracePage traceId={traceId} />
  if (isDashboardPreviewEnabled()) return <PreviewTraceInspectorPage />
  return null
}
