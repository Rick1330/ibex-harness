"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { ActionLedgerEntry } from "@/lib/directives/types"
import { panelClass } from "@/components/sessions/dashboard-shell"

export function ActionLedger({ entries }: { entries: ActionLedgerEntry[] }) {
  const sorted = [...entries].sort(
    (a, b) => Date.parse(b.at) - Date.parse(a.at),
  )

  return (
    <Card id="action-ledger" className={panelClass}>
      <CardHeader className="gap-1 border-b px-4 py-3">
        <CardTitle className="text-[13px] font-medium">Action Ledger</CardTitle>
        <p className="text-[13px] text-muted-foreground">
          Every mutation — actor, timestamp, reason, before/after. Duplicate
          submits share one idempotency key (one entry, not two).
        </p>
      </CardHeader>
      <CardContent className="px-4 py-3">
        {sorted.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">No actions yet.</p>
        ) : (
          <ul className="space-y-2.5">
            {sorted.map((e) => (
              <li
                key={e.id}
                className="grid gap-0.5 border-b border-border/60 pb-2.5 last:border-0 last:pb-0 font-mono text-[13px] leading-5"
              >
                <div className="flex flex-wrap gap-x-2 text-muted-foreground">
                  <span>{e.at.replace("T", " ").slice(0, 16)}</span>
                  <span>{e.actor}</span>
                  <span className="text-foreground/80">{e.kind}</span>
                </div>
                <div>{e.summary}</div>
                {(e.before_version != null || e.after_version != null) && (
                  <div className="text-[13px] text-muted-foreground">
                    v{e.before_version ?? "—"} → v{e.after_version ?? "—"}
                  </div>
                )}
                {e.reason && (
                  <div className="text-[13px] text-muted-foreground">
                    reason: {e.reason}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
