"use client"

import Link from "next/link"
import { useParams } from "next/navigation"

import { DirectiveDetailView } from "@/components/directives/directive-detail"
import {
  DashboardShell,
  pagePad,
  panelClass,
} from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { DIRECTIVE_BY_ID } from "@/lib/directives/fixtures"

export default function DirectiveDetailPage() {
  const params = useParams<{ directiveId: string }>()
  const directive = DIRECTIVE_BY_ID[params.directiveId]

  return (
    <DashboardShell>
      <div className={pagePad}>
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <Button asChild size="sm" variant="ghost" className="-ml-2">
            <Link href="/dashboard/directives">← Directives</Link>
          </Button>
        </div>

        {!directive ? (
          <Card className={panelClass}>
            <CardContent className="px-4 py-10 text-center">
              <div className="text-[13px] font-medium">Directive not found</div>
              <p className="mt-1 text-[13px] text-muted-foreground">
                Unknown or out-of-org{" "}
                <span className="font-mono">{params.directiveId}</span> — never
                &quot;found but forbidden.&quot;
              </p>
              <Button asChild size="sm" className="mt-3">
                <Link href="/dashboard/directives">Back to Directives</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <DirectiveDetailView directive={directive} />
        )}
      </div>
    </DashboardShell>
  )
}
