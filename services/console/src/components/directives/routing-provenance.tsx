"use client"

import Link from "next/link"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { RoutingProvenance } from "@/lib/directives/types"
import { cn } from "@/lib/utils"

export function RoutingProvenancePanel({
  routing,
}: {
  routing: RoutingProvenance
}) {
  return (
    <Card className={panelClass}>
      <CardHeader className="gap-1 border-b px-4 py-3">
        <CardTitle className="text-[13px] font-medium">
          Routing decision provenance
        </CardTitle>
        <p className="text-[13px] text-muted-foreground">
          Per-request candidate lane — same exclusion discipline as Trace
          Inspector. Links back via request_id.
        </p>
      </CardHeader>
      <CardContent className="space-y-3 px-4 py-3 text-[13px] leading-5">
        <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[13px] text-muted-foreground">
          <Link
            href={`/dashboard/explore/t/trace_a91f7c`}
            className="hover:underline"
          >
            {routing.request_id}
          </Link>
          <span>{routing.session_id}</span>
          <span>directive v{routing.resolved_directive_version}</span>
          <span>bucket {routing.sticky_hash_bucket}</span>
        </div>
        <div className="font-mono text-[13px] text-muted-foreground">
          catalog {routing.capability_catalog_version} · credentials{" "}
          {routing.credential_scope}
        </div>
        {routing.fallback_trigger && (
          <p className="rounded-md border border-amber-600/30 bg-amber-500/5 px-3 py-2 text-[13px] text-amber-900 dark:text-amber-200">
            Fallback trigger: {routing.fallback_trigger}
          </p>
        )}
        <ul className="space-y-1.5 font-mono text-[13px]">
          {routing.candidates.map((c) => (
            <li
              key={`${c.provider}:${c.model}`}
              className={cn(
                "rounded-md border px-3 py-2",
                c.disposition === "selected"
                  ? "border-foreground/30"
                  : "border-border text-muted-foreground",
              )}
            >
              <span className="text-foreground">
                {c.disposition === "selected" ? "→ " : ""}
                {c.provider}/{c.model}
              </span>
              <div className="mt-0.5 text-[13px]">{c.reason}</div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
