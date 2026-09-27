"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"

import { DashboardShell, pagePad } from "@/components/sessions/dashboard-shell"
import { Skeleton } from "@/components/ui/skeleton"
import { FAILURE_LIST, SESSION_LIST, TRACE_LIST } from "@/lib/explore/fixtures"
import type { ExploreTab, QueryChip } from "@/lib/explore/types"
import {
  filterTraces,
  parseChips,
  parseTab,
} from "@/app/dashboard/explore/preview-query"
import {
  PreviewContent,
  type PreviewViewState,
} from "@/app/dashboard/explore/preview-content"

type PreviewSync = { chips?: QueryChip[]; tab?: ExploreTab }

function ExploreWorkbench() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const chips = React.useMemo(
    () => parseChips(searchParams.get("q")),
    [searchParams],
  )
  const tab = parseTab(searchParams.get("tab"))
  const [view, setView] = React.useState<PreviewViewState>("loading")
  const [hoveredId, setHoveredId] = React.useState<string | null>(null)
  const locked = React.useRef(false)

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      if (!locked.current) setView("success")
    }, 700)
    return () => {
      window.clearTimeout(timer)
    }
  }, [])

  const syncUrl = React.useCallback(
    (next: PreviewSync) => {
      const params = new URLSearchParams()
      const nextChips = next.chips ?? chips
      if (nextChips.length) {
        params.set(
          "q",
          nextChips
            .map((chip) =>
              chip.field === "text"
                ? chip.value
                : `${chip.field}:${chip.value}`,
            )
            .join(" "),
        )
      }
      params.set("tab", next.tab ?? tab)
      router.replace(`/dashboard/explore?${params.toString()}`, {
        scroll: false,
      })
    },
    [chips, router, tab],
  )

  const traces = filterTraces(TRACE_LIST, chips)
  const hovered = traces.find((trace) => trace.trace_id === hoveredId) ?? null
  const counts = {
    traces: traces.length,
    sessions: SESSION_LIST.length,
    failures: FAILURE_LIST.length,
  }
  const preview = (nextView: PreviewViewState) => {
    locked.current = true
    setView(nextView)
  }
  const retry = () => {
    locked.current = true
    setView("loading")
    window.setTimeout(() => {
      setView("success")
    }, 800)
  }
  const saveView = () => {
    syncUrl({})
    void navigator.clipboard.writeText(window.location.href)
    toast.success("Saved view URL copied", {
      description:
        "Pin it under ★ Pinned — views are URLs, not server objects.",
    })
  }

  return (
    <PreviewContent
      view={view}
      chips={chips}
      tab={tab}
      traces={traces}
      counts={counts}
      hoveredId={hoveredId}
      hovered={hovered}
      onPreview={preview}
      onRetry={retry}
      onChipsChange={(next) => {
        syncUrl({ chips: next })
      }}
      onSaveView={saveView}
      onTabChange={(next) => {
        syncUrl({ tab: next })
      }}
      onHover={setHoveredId}
      onSelect={(id) => {
        router.push(`/dashboard/explore/t/${id}`)
      }}
    />
  )
}

export default function PreviewExplorePage() {
  return (
    <DashboardShell>
      <React.Suspense
        fallback={
          <div className={pagePad}>
            <Skeleton className="h-24 w-full rounded-lg" />
          </div>
        }
      >
        <ExploreWorkbench />
      </React.Suspense>
    </DashboardShell>
  )
}
