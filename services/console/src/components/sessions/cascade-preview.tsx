"use client"

import Link from "next/link"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { CopyId } from "@/components/explore/copy-id"
import { PrivilegedActionButton } from "@/components/sessions/privileged-gate"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { CascadePreview } from "@/lib/sessions/types"
import { privilegedActionsEnabled } from "@/lib/sessions/types"

export function CascadePreviewPanel({ preview }: { preview: CascadePreview }) {
  const enabled = privilegedActionsEnabled()

  return (
    <Card className={panelClass}>
      <CardHeader className="gap-1 border-b px-4 py-3">
        <CardTitle className="text-[13px] font-medium">
          {preview.kind === "delete" ? "Delete" : "Export"} preview —{" "}
          <span className="font-mono">{preview.target_id}</span>
        </CardTitle>
        <p className="text-[13px] text-muted-foreground">
          Cascade preview = execution scope. Divergence is a release blocker
          (F4-019).
        </p>
      </CardHeader>
      <CardContent className="space-y-3 px-4 py-3 text-[13px] leading-5">
        <div>
          <div className="mb-1.5 text-[13px] text-muted-foreground">
            Will remove from:
          </div>
          <ul className="space-y-1.5 font-mono text-[13px]">
            {preview.stores.map((s) => (
              <li key={s.store} className="flex flex-wrap gap-x-2">
                <span>{s.ok ? "✓" : "⚠"}</span>
                <span>{s.store}</span>
                <span className="text-muted-foreground">({s.detail})</span>
                <span className="tabular-nums">
                  {s.rows_or_objects.toLocaleString()} {s.unit}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="font-mono text-[13px]">
          Legal hold check: {preview.legal_hold_note}
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <PrivilegedActionButton>
            Confirm & Authenticate →
          </PrivilegedActionButton>
          {enabled && (
            <span className="inline-flex items-center gap-1 text-[13px] text-muted-foreground">
              Step-up authentication required to confirm
            </span>
          )}
        </div>
        <p className="text-[13px] text-muted-foreground">
          Receipts on completion are per-store verified / not_applicable /
          store_unreachable — never a bare &quot;Success&quot; toast. See{" "}
          <Link href="#jobs" className="underline-offset-2 hover:underline">
            jobs
          </Link>
          .
        </p>
        <CopyId
          value={preview.target_id}
          label="target"
          className="text-[13px] text-muted-foreground"
        />
      </CardContent>
    </Card>
  )
}
