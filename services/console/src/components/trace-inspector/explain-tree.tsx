"use client"

import { panelClass } from "@/components/sessions/dashboard-shell"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { allowsFullWaterfall } from "@/lib/explore/fixtures"
import { VIZ } from "@/lib/explore/viz-colors"
import type {
  CandidateScore,
  ScoreSchema,
  ScoreTerm,
} from "@/lib/explore/types"
import { cn } from "@/lib/utils"

const TERM_STYLE: Record<
  ScoreTerm["name"],
  { bar: string; chip: string; label: string }
> = {
  relevance: {
    bar: VIZ["score-a"].fill,
    chip: cn(VIZ["score-a"].fill, VIZ["score-a"].text),
    label: VIZ["score-a"].label,
  },
  recency: {
    bar: VIZ["score-b"].fill,
    chip: cn(VIZ["score-b"].fill, VIZ["score-b"].text),
    label: VIZ["score-b"].label,
  },
  usefulness: {
    bar: VIZ["score-c"].fill,
    chip: cn(VIZ["score-c"].fill, VIZ["score-c"].text),
    label: VIZ["score-c"].label,
  },
  confidence: {
    bar: VIZ["score-d"].fill,
    chip: cn(VIZ["score-d"].fill, VIZ["score-d"].text),
    label: VIZ["score-d"].label,
  },
  frequency: {
    bar: VIZ["score-e"].fill,
    chip: cn(VIZ["score-e"].fill, VIZ["score-e"].text),
    label: VIZ["score-e"].label,
  },
}

/**
 * Layer 3 — Explain tree.
 *
 * Contractual honesty: never render a five-component waterfall against
 * interim_v1. That is exactly the dishonest UI F4-009 / F4-025 prevent.
 */
export function ExplainTree({
  score,
  scoreSchema,
  candidateLabel,
}: {
  score: CandidateScore | null
  scoreSchema: ScoreSchema
  candidateLabel: string
}) {
  const fullAllowed = allowsFullWaterfall(scoreSchema)

  return (
    <Card id="explain-tree" className={panelClass}>
      <CardHeader className="border-b pb-4">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>Explain tree</CardTitle>
          <SchemaBadge schema={scoreSchema} />
          {!fullAllowed && (
            <span className="rounded-full border border-amber-600/40 px-2 py-0.5 font-mono text-[11px] text-amber-800 dark:text-amber-300">
              degraded · two-term blend only
            </span>
          )}
        </div>
        <CardDescription>
          {candidateLabel} — score / rank / resource-cost stay visually distinct
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-5">
        {!score ? (
          <p className="text-sm text-muted-foreground">
            No score for this candidate (filtered / failed). Disposition is
            categorical — never shown as a numeric zero.
          </p>
        ) : score.score_schema === "v1_full" && fullAllowed ? (
          <FullWaterfall score={score} />
        ) : score.score_schema === "interim_v1" || !fullAllowed ? (
          <InterimBlend
            score={
              score.score_schema === "interim_v1"
                ? score
                : {
                    score_schema: "interim_v1",
                    relevance: 0,
                    relevance_weight: 0,
                    recency: 0,
                    recency_weight: 0,
                    composite: score.composite,
                    detail:
                      "Payload claimed v1_full but gate is closed — refusing five-term render.",
                  }
            }
          />
        ) : (
          <p className="text-sm text-muted-foreground">
            Unsupported score payload.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export function SchemaBadge({ schema }: { schema: ScoreSchema }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-mono text-[11px]",
        schema === "v1_full"
          ? "border-foreground/30"
          : "border-amber-600/40 text-amber-800 dark:text-amber-300",
      )}
    >
      score_schema:{schema}
    </Badge>
  )
}

function FullWaterfall({
  score,
}: {
  score: Extract<CandidateScore, { score_schema: "v1_full" }>
}) {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
      <div className="flex flex-col gap-5">
        <div className="rounded-lg border bg-muted/30 p-4">
          <div className="text-[12px] font-medium tracking-[0.14em] text-muted-foreground uppercase">
            Composite
          </div>
          <div className="mt-1 flex items-end gap-3">
            <span className="font-serif text-5xl tabular-nums tracking-tight">
              {score.composite.toFixed(2)}
            </span>
            <span className="mb-1.5 font-mono text-[12px] text-muted-foreground">
              = Σ weight × term
            </span>
          </div>
          <div className="mt-4 flex h-5 overflow-hidden rounded-md border border-border/60 bg-muted/40">
            {score.terms.map((term) => (
              <div
                key={term.name}
                className={cn(
                  "h-full border-r border-background/40 last:border-r-0",
                  TERM_STYLE[term.name].bar,
                )}
                style={{
                  width: `${(term.contribution / Math.max(score.composite, 0.001)) * 100}%`,
                }}
                title={`${TERM_STYLE[term.name].label}: ${term.contribution.toFixed(3)}`}
              />
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {score.terms.map((term) => (
              <span
                key={term.name}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 font-mono text-[11px] font-medium",
                  TERM_STYLE[term.name].chip,
                )}
              >
                <span className="opacity-90">
                  {TERM_STYLE[term.name].label}
                </span>
                {term.contribution.toFixed(3)}
              </span>
            ))}
          </div>
        </div>

        <p className="font-mono text-[12px] leading-relaxed text-muted-foreground">
          0.40×similarity + 0.25×recency + 0.20×confidence + 0.10×trust +
          0.05×label
        </p>
      </div>

      <div className="flex flex-col gap-2.5">
        {score.terms.map((term, i) => (
          <div
            key={term.name}
            className="rise rounded-lg border bg-card p-3"
            style={{ animationDelay: `${i * 50}ms` }}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "size-2 shrink-0 rounded-[2px]",
                      TERM_STYLE[term.name].bar,
                    )}
                  />
                  <span className="text-sm font-medium">
                    {TERM_STYLE[term.name].label}
                  </span>
                  <span className="font-mono text-[11px] text-muted-foreground">
                    ×{term.weight.toFixed(2)}
                  </span>
                </div>
                {term.detail && (
                  <p className="mt-1 font-mono text-[11px] leading-snug text-muted-foreground">
                    {term.detail}
                  </p>
                )}
              </div>
              <div className="text-right">
                <div className="font-mono text-sm font-medium tabular-nums">
                  {term.contribution.toFixed(3)}
                </div>
                <div className="font-mono text-[11px] text-muted-foreground tabular-nums">
                  raw {term.raw.toFixed(2)}
                </div>
              </div>
            </div>
            <div className="mt-2.5 h-2 overflow-hidden rounded-sm bg-muted">
              <div
                className={cn("h-full rounded-sm", TERM_STYLE[term.name].bar)}
                style={{ width: `${Math.min(100, term.raw * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function InterimBlend({
  score,
}: {
  score: Extract<CandidateScore, { score_schema: "interim_v1" }>
}) {
  const terms = [
    {
      name: "relevance" as const,
      raw: score.relevance,
      weight: score.relevance_weight,
      contribution: score.relevance * score.relevance_weight,
    },
    {
      name: "recency" as const,
      raw: score.recency,
      weight: score.recency_weight,
      contribution: score.recency * score.recency_weight,
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <p className="rounded-lg border border-muted px-4 py-3 text-sm text-muted-foreground">
        Interim two-term payload. Full five-component waterfall renders when{" "}
        <span className="font-mono">score_schema</span> is{" "}
        <span className="font-mono">v1_full</span>.
      </p>

      <div className="rounded-lg border bg-muted/30 p-4">
        <div className="text-[12px] font-medium tracking-[0.14em] text-muted-foreground uppercase">
          Interim composite
        </div>
        <div className="mt-1 font-serif text-4xl tabular-nums tracking-tight">
          {score.composite.toFixed(3)}
        </div>
        <div className="mt-4 flex h-4 overflow-hidden rounded-md border border-border/60 bg-muted/40">
          {terms.map((term) => (
            <div
              key={term.name}
              className={cn(
                "h-full border-r border-background/40 last:border-r-0",
                TERM_STYLE[term.name].bar,
              )}
              style={{
                width: `${(term.contribution / Math.max(score.composite, 0.001)) * 100}%`,
              }}
            />
          ))}
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {terms.map((term) => (
          <div key={term.name} className="rounded-lg border p-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">
                {TERM_STYLE[term.name].label}
              </span>
              <span className="font-mono text-sm tabular-nums">
                {term.contribution.toFixed(3)}
              </span>
            </div>
            <p className="mt-1 font-mono text-[12px] text-muted-foreground">
              {term.raw.toFixed(2)} × {term.weight.toFixed(2)}
            </p>
            <div className="mt-2 h-2 overflow-hidden rounded-sm bg-muted">
              <div
                className={cn("h-full rounded-sm", TERM_STYLE[term.name].bar)}
                style={{ width: `${Math.min(100, term.raw * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      {score.detail && (
        <p className="font-mono text-[11px] text-muted-foreground">
          {score.detail}
        </p>
      )}
    </div>
  )
}
