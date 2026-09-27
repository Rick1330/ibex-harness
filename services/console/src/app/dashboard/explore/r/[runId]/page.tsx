import { LiveRunPage } from "@/app/dashboard/explore/r/[runId]/live-page"
import { isDashboardPreviewEnabled, isLiveD1Enabled } from "@/lib/classification"

export const dynamic = "force-dynamic"

export default async function RunDetailPage({
  params,
  searchParams,
}: Readonly<{
  params: Promise<{ runId: string }>
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}>) {
  const { runId } = await params
  if (isLiveD1Enabled()) return <LiveRunPage runId={runId} searchParams={searchParams} />
  if (isDashboardPreviewEnabled()) {
    return (
      <main className="p-8">
        <p className="text-sm text-muted-foreground">
          Run detail is live-only. Open Explore preview fixtures via trace IDs instead.
        </p>
      </main>
    )
  }
  return null
}
