"use client"

import { panelClass } from "@/components/sessions/dashboard-shell"
import * as React from "react"
import Link from "next/link"
import { IconArrowRight } from "@tabler/icons-react"

import { CopyId } from "@/components/explore/copy-id"
import {
  EvidenceBadgeRow,
  StatusBadge,
} from "@/components/explore/evidence-badges"
import { LatencyMiniBar } from "@/components/explore/latency-bar"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { TraceListItem } from "@/lib/explore/types"

/** Hover preview — content-sized card, never stretched to page height. */
export function TracePreviewPanel({ trace }: { trace: TraceListItem | null }) {
  if (!trace) {
    return (
      <Card className={panelClass}>
        <CardContent className="px-4 py-4 text-[13px] leading-5 text-muted-foreground">
          Hover a row to preview. Click to open the inspector.
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={panelClass}>
      <CardHeader className="gap-1.5 border-b px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[13px] text-muted-foreground">Preview</div>
            <CardTitle className="mt-0.5 truncate font-mono text-[13px] font-medium leading-5">
              <CopyId value={trace.trace_id} label="trace_id" />
            </CardTitle>
          </div>
          <StatusBadge status={trace.status} />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 px-4 py-3">
        <div className="flex flex-wrap gap-1.5 font-mono text-[13px] leading-5">
          <Chip href="#">{trace.agent}</Chip>
          <Chip href="#">{trace.session_id}</Chip>
          <Chip href="#">{trace.model}</Chip>
          <Chip href="#">{trace.provider}</Chip>
        </div>

        <div className="grid grid-cols-2 gap-3 text-[13px] leading-5">
          <div>
            <div className="text-[13px] text-muted-foreground">Tokens</div>
            <div className="mt-0.5 font-mono text-[13px] tabular-nums">
              {trace.tokens.prompt + trace.tokens.completion}
              <span className="ml-1 text-[13px] text-muted-foreground">
                ({trace.tokens.prompt}/{trace.tokens.completion})
              </span>
            </div>
          </div>
          <div>
            <div className="text-[13px] text-muted-foreground">Latency</div>
            <div className="mt-0.5">
              <LatencyMiniBar
                auth_ms={trace.latency.auth_ms}
                context_ms={trace.latency.context_retrieve_ms}
                provider_ms={trace.latency.provider_ms}
                stream_ms={trace.latency.stream_ms}
                total_ms={trace.latency.total_ms}
              />
            </div>
          </div>
        </div>

        <EvidenceBadgeRow evidence={trace.evidence} />

        <Button asChild size="sm" className="w-full text-[13px]">
          <Link href={`/dashboard/explore/t/${trace.trace_id}`}>
            Open inspector
            <IconArrowRight className="size-3.5" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  )
}

function Chip({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="rounded-full border bg-muted/50 px-2 py-0.5 hover:bg-muted"
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </Link>
  )
}
