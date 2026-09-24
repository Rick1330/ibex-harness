"use client"

import Link from "next/link"
import { useParams } from "next/navigation"

import { IncidentDetailView } from "@/components/incidents/incident-detail"
import {
  DashboardShell,
  pagePad,
  panelClass,
} from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { INCIDENT_BY_ID } from "@/lib/incidents/fixtures"

export default function IncidentDetailPage() {
  const params = useParams<{ incidentId: string }>()
  const incident = INCIDENT_BY_ID[params.incidentId]

  return (
    <DashboardShell>
      <div className={pagePad}>
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <Button asChild size="sm" variant="ghost" className="-ml-2">
            <Link href="/dashboard/incidents">← Incidents</Link>
          </Button>
        </div>

        {!incident ? (
          <Card className={panelClass}>
            <CardContent className="px-4 py-10 text-center">
              <div className="text-[13px] font-medium">Incident not found</div>
              <p className="mt-1 text-[13px] text-muted-foreground">
                Unknown or out-of-org{" "}
                <span className="font-mono">{params.incidentId}</span> returns
                empty / 404 — never &quot;found but forbidden.&quot;
                Cross-tenant isolation is release-gated.
              </p>
              <Button asChild size="sm" className="mt-3">
                <Link href="/dashboard/incidents">Back to Incidents</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <IncidentDetailView incident={incident} />
        )}
      </div>
    </DashboardShell>
  )
}
