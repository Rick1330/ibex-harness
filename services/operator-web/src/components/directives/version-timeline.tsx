"use client"

import type { DirectiveVersion } from "@/lib/directives/types"
import {
  LifecycleBadge,
  RegressionBadge,
} from "@/components/directives/status-badges"
import { cn } from "@/lib/utils"

export function VersionTimeline({
  versions,
  selected,
  onSelect,
}: {
  versions: DirectiveVersion[]
  selected: number
  onSelect: (version: number) => void
}) {
  return (
    <ol className="relative space-y-0 border-l border-border pl-4">
      {versions.map((v) => {
        const active = v.version === selected
        const isLive = v.status === "active"
        return (
          <li key={v.version} className="relative pb-5 last:pb-0">
            <span
              className={cn(
                "absolute -left-[21px] top-1 size-2.5 rounded-full border-2 border-background",
                isLive ? "bg-foreground" : "bg-muted-foreground/50",
              )}
            />
            <button
              type="button"
              onClick={() => onSelect(v.version)}
              className={cn(
                "w-full rounded-md border px-3 py-2 text-left transition-colors",
                active
                  ? "border-foreground/40 bg-muted/40"
                  : "hover:bg-muted/30",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[13px] font-medium">
                  v{v.version}
                </span>
                <LifecycleBadge status={v.status} />
              </div>
              <p className="mt-1 font-mono text-[13px] leading-5 text-muted-foreground">
                {v.promoted_at
                  ? `promoted ${v.promoted_at.slice(0, 10)} by ${v.promoted_by}`
                  : `created ${v.created_at.slice(0, 10)} by ${v.created_by}`}
              </p>
              {v.status === "deprecated" || v.status === "active" ? (
                <div className="mt-1.5">
                  <RegressionBadge
                    status={v.regression_status}
                    passed={v.scenarios_passed}
                    total={v.scenarios_total}
                  />
                </div>
              ) : null}
              {v.revoked_reason && (
                <p className="mt-1.5 text-[13px] leading-5 text-destructive">
                  reason: &quot;{v.revoked_reason}&quot;
                </p>
              )}
              <p className="mt-1 font-mono text-[13px] text-muted-foreground">
                hash {v.content_hash} · {v.content_tokens} tok · immutable
              </p>
            </button>
          </li>
        )
      })}
    </ol>
  )
}
