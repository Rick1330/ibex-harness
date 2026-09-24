"use client"

import * as React from "react"
import Link from "next/link"
import { IconChevronDown, IconChevronRight } from "@tabler/icons-react"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { CopyId } from "@/components/explore/copy-id"
import { exploreTable } from "@/components/explore/table-styles"
import { PrivilegedActionButton } from "@/components/sessions/privileged-gate"
import { TurnKindBadge } from "@/components/sessions/status-badges"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import type { SessionDetail, SessionTurn } from "@/lib/sessions/types"
import { cn } from "@/lib/utils"

export function SessionTimeline({ session }: { session: SessionDetail }) {
  const [open, setOpen] = React.useState<number | null>(2)

  return (
    <div className="flex flex-col gap-3">
      {session.embedding_mismatch && (
        <p className="rounded-md border border-amber-600/30 bg-amber-500/5 px-3 py-2 text-[13px] leading-5 text-amber-900 dark:text-amber-200">
          Embedding/ranking mismatch — retrieval model/version no longer matches
          current config. Scores may look confident but be wrong.
        </p>
      )}

      <Card className={panelClass}>
        <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 text-[13px]">
          <CopyId
            value={session.session_id}
            label="session_id"
            className="font-medium"
          />
          <span className="font-mono text-muted-foreground">
            {session.agent} · directive v{session.directive_version} ·{" "}
            {session.turn_count} turns · {session.duration_ms}ms
          </span>
          <div className="ml-auto flex flex-wrap gap-2">
            <PrivilegedActionButton>Export…</PrivilegedActionButton>
            <PrivilegedActionButton>Delete…</PrivilegedActionButton>
            <Button asChild size="sm" variant="outline">
              <Link href={`#replay`}>Safe replay</Link>
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className={panelClass}>
        <CardContent className="divide-y p-0">
          {session.turns.map((turn) => (
            <TurnRow
              key={turn.sequence_number}
              turn={turn}
              expanded={open === turn.sequence_number}
              onToggle={() =>
                setOpen((cur) =>
                  cur === turn.sequence_number ? null : turn.sequence_number,
                )
              }
            />
          ))}
        </CardContent>
      </Card>
    </div>
  )
}

function TurnRow({
  turn,
  expanded,
  onToggle,
}: {
  turn: SessionTurn
  expanded: boolean
  onToggle: () => void
}) {
  const special =
    turn.evidence_state === "missing" ||
    turn.evidence_state === "redacted" ||
    turn.evidence_state === "sampled"

  return (
    <div
      className={cn(
        special && "bg-amber-500/[0.04]",
        turn.kind === "checkpoint" && "bg-muted/30",
      )}
    >
      <button
        type="button"
        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-muted/40"
        onClick={onToggle}
      >
        {expanded ? (
          <IconChevronDown className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        ) : (
          <IconChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        )}
        <span className="w-8 shrink-0 font-mono text-[13px] tabular-nums text-muted-foreground">
          #{turn.sequence_number}
        </span>
        <TurnKindBadge kind={turn.kind} />
        <span className="min-w-0 flex-1 font-mono text-[13px] leading-5">
          {turn.summary}
        </span>
        <span className="shrink-0 font-mono text-[13px] text-muted-foreground">
          {turn.at.slice(11, 23)}
        </span>
      </button>

      {expanded && <TurnDetail turn={turn} />}
    </div>
  )
}

function TurnDetail({ turn }: { turn: SessionTurn }) {
  if (
    turn.evidence_state === "missing" ||
    turn.evidence_state === "redacted" ||
    turn.evidence_state === "sampled"
  ) {
    return (
      <div className="border-t px-4 py-3 pl-14 text-[13px] leading-5 text-amber-900 dark:text-amber-200">
        Explicit {turn.evidence_state} event — not an empty gap. Something was
        recorded as {turn.evidence_state}; do not infer &quot;nothing
        happened.&quot;
      </div>
    )
  }

  return (
    <div className="space-y-3 border-t px-4 py-3 pl-14 text-[13px] leading-5">
      {turn.context_assembly && (
        <div>
          <div className="mb-1 text-[13px] text-muted-foreground">
            Context assembly
          </div>
          <div className="font-mono text-[13px]">
            directive {turn.context_assembly.directive}/
            {turn.context_assembly.budget} · history{" "}
            {turn.context_assembly.history}/{turn.context_assembly.budget} ·
            memories {turn.context_assembly.memories}/
            {turn.context_assembly.budget} · tools {turn.context_assembly.tools}
            /{turn.context_assembly.budget}
          </div>
        </div>
      )}

      {turn.memories && turn.memories.length > 0 && (
        <div>
          <div className="mb-1.5 text-[13px] text-muted-foreground">
            Memories injected — similarity ≠ composite rank
          </div>
          <div className="overflow-hidden rounded-md border">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b bg-muted/30">
                  <th className={exploreTable.head}>memory</th>
                  <th className={exploreTable.head}>sim</th>
                  <th className={exploreTable.head}>composite</th>
                  <th className={exploreTable.head}>rank</th>
                  <th className={exploreTable.head}>cat</th>
                </tr>
              </thead>
              <tbody>
                {turn.memories.map((m) => (
                  <tr key={m.memory_id} className="border-b last:border-0">
                    <td className={exploreTable.cell}>
                      <Link
                        href={`/dashboard/memories/${m.memory_id}`}
                        className="font-mono hover:underline"
                      >
                        {m.memory_id}
                      </Link>
                    </td>
                    <td
                      className={`${exploreTable.cell} font-mono tabular-nums`}
                    >
                      {m.retrieval_similarity.toFixed(2)}
                    </td>
                    <td
                      className={`${exploreTable.cell} font-mono tabular-nums`}
                    >
                      {m.composite_score.toFixed(2)}
                    </td>
                    <td
                      className={`${exploreTable.cell} font-mono tabular-nums`}
                    >
                      {m.final_rank}
                    </td>
                    <td className={`${exploreTable.cell} font-mono`}>
                      {m.category}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {turn.conversation_preview && (
        <details className="rounded-md border px-3 py-2">
          <summary className="cursor-pointer text-[13px] text-muted-foreground">
            Conversation (collapsed)
          </summary>
          <p className="mt-2 text-[13px] leading-5">
            {turn.conversation_preview}
          </p>
        </details>
      )}

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
        {turn.trace_id && (
          <Link
            href={`/dashboard/explore/t/${turn.trace_id}`}
            className="hover:underline"
          >
            → Trace Inspector ({turn.trace_id})
          </Link>
        )}
        {turn.directive_version != null && (
          <Link href="#" className="hover:underline">
            → Directive v{turn.directive_version} ({turn.directive_hash ?? "—"})
            diff
          </Link>
        )}
        {turn.checkpoint_id && (
          <span className="font-mono">checkpoint {turn.checkpoint_id}</span>
        )}
        <span title="Raw JSON requires raw:read + recent auth + audit">
          View raw (gated)
        </span>
      </div>
    </div>
  )
}
