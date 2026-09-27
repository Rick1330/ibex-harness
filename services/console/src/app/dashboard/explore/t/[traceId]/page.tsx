import { LiveTracePage } from "@/app/dashboard/explore/t/[traceId]/live-page"
import PreviewTraceInspectorPage from "@/app/dashboard/explore/t/[traceId]/preview-page"
import { isDashboardPreviewEnabled, isLiveD1Enabled } from "@/lib/classification"

export const dynamic = "force-dynamic"

export default async function TraceInspectorPage({
  params,
  searchParams,
}: Readonly<{
  params: Promise<{ traceId: string }>
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}>) {
  const { traceId } = await params
  if (isLiveD1Enabled()) return <LiveTracePage traceId={traceId} searchParams={searchParams} />
  if (isDashboardPreviewEnabled()) return <PreviewTraceInspectorPage />
  return null
}
