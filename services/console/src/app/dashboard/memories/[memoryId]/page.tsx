"use client"

import Link from "next/link"
import { useParams } from "next/navigation"

import {
  DashboardShell,
  pagePad,
  panelClass,
} from "@/components/sessions/dashboard-shell"
import { MemoryDetailView } from "@/components/sessions/memory-detail"
import { PrivilegedGateBanner } from "@/components/sessions/privileged-gate"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { MEMORY_BY_ID, MEMORY_LIST } from "@/lib/sessions/fixtures"
import type { MemoryDetail } from "@/lib/sessions/types"

function resolveMemory(id: string): MemoryDetail | null {
  if (MEMORY_BY_ID[id]) return MEMORY_BY_ID[id]
  const list = MEMORY_LIST.find((m) => m.memory_id === id)
  if (!list) return null
  return {
    ...list,
    content: list.preview,
    lineage: [],
    lineage_truncated: false,
    embedding_model: "text-embedding-3-large",
    embedding_version: "v2",
    current_embedding_version: "v2",
    embedding_mismatch: false,
    retrieval_note:
      "similarity ≠ rank — composite reordering applied after retrieval.",
  }
}

export default function MemoryDetailPage() {
  const params = useParams<{ memoryId: string }>()
  const memory = resolveMemory(params.memoryId)

  return (
    <DashboardShell>
      <div className={pagePad}>
        <Button asChild size="sm" variant="ghost" className="-ml-2 w-fit">
          <Link href="/dashboard/memories">← Memories</Link>
        </Button>

        {!memory ? (
          <Card className={panelClass}>
            <CardContent className="px-4 py-10 text-center">
              <div className="text-[13px] font-medium">Memory not found</div>
              <p className="mt-1 text-[13px] text-muted-foreground">
                Unknown or out-of-org{" "}
                <span className="font-mono">{params.memoryId}</span> returns
                empty / 404.
              </p>
            </CardContent>
          </Card>
        ) : (
          <>
            <PrivilegedGateBanner />
            <MemoryDetailView memory={memory} />
          </>
        )}
      </div>
    </DashboardShell>
  )
}
