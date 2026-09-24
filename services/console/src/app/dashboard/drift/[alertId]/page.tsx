"use client"

import Link from "next/link"
import { useParams } from "next/navigation"

import { DriftAlertDetailView } from "@/components/drift/drift-alert-detail"
import {
  DashboardShell,
  pagePad,
  panelClass,
} from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { getDriftAlert } from "@/lib/drift/fixtures"

export default function DriftAlertDetailPage() {
  const params = useParams<{ alertId: string }>()
  const alert = getDriftAlert(params.alertId)

  return (
    <DashboardShell>
      <div className={pagePad}>
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <Button asChild size="sm" variant="ghost" className="-ml-2">
            <Link href="/dashboard/drift">← Drift Alerts</Link>
          </Button>
        </div>

        {!alert ? (
          <Card className={panelClass}>
            <CardContent className="px-4 py-10 text-center">
              <div className="text-[13px] font-medium">Alert not found</div>
              <p className="mt-1 text-[13px] text-muted-foreground">
                Unknown or out-of-org{" "}
                <span className="font-mono">{params.alertId}</span> returns
                empty / 404 — never &quot;found but forbidden.&quot;
              </p>
              <Button asChild size="sm" className="mt-3">
                <Link href="/dashboard/drift">Back to Drift Alerts</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <DriftAlertDetailView alert={alert} />
        )}
      </div>
    </DashboardShell>
  )
}
