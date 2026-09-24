"use client"

import Link from "next/link"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { AssessmentBadge } from "@/components/directives/status-badges"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { BehavioralDiff, TextDiff } from "@/lib/directives/types"
import { cn } from "@/lib/utils"

export function DiffViewer({
  diff,
  behavioral,
  mode,
  onModeChange,
}: {
  diff: TextDiff
  behavioral: BehavioralDiff
  mode: "unified" | "split"
  onModeChange: (m: "unified" | "split") => void
}) {
  return (
    <Card className={panelClass}>
      <CardHeader className="gap-2 border-b px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-[13px] font-medium">
            Diff: v{diff.from_version} → v{diff.to_version}
          </CardTitle>
          <div className="ml-auto flex gap-1">
            <Button
              size="sm"
              variant={mode === "unified" ? "secondary" : "ghost"}
              className="h-7 px-2 text-[13px]"
              onClick={() => onModeChange("unified")}
            >
              Unified
            </Button>
            <Button
              size="sm"
              variant={mode === "split" ? "secondary" : "ghost"}
              className="h-7 px-2 text-[13px]"
              onClick={() => onModeChange("split")}
            >
              Split
            </Button>
          </div>
        </div>
        <p className="font-mono text-[13px] text-muted-foreground">
          +{diff.additions} / −{diff.deletions} · token_delta{" "}
          {diff.token_delta > 0 ? "+" : ""}
          {diff.token_delta}
        </p>
      </CardHeader>
      <CardContent className="space-y-4 px-4 py-3">
        {mode === "unified" ? (
          <UnifiedDiff diff={diff} />
        ) : (
          <SplitDiff diff={diff} />
        )}

        <div className="border-t pt-3">
          <div className="mb-2 text-[13px] font-medium">
            Behavioral comparison
          </div>
          <p className="mb-3 font-mono text-[13px] text-muted-foreground">
            {behavioral.test_scenarios_run} scenarios ·{" "}
            {behavioral.behavior_changed} changed ·{" "}
            {behavioral.behavior_unchanged} unchanged
          </p>
          <ul className="space-y-3">
            {behavioral.scenarios.map((s) => (
              <li
                key={s.scenario_id}
                className="rounded-md border px-3 py-2 text-[13px] leading-5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  {s.is_critical ? (
                    <span className="font-mono text-[13px] text-amber-800 dark:text-amber-200">
                      🔒 is_critical
                    </span>
                  ) : (
                    <span className="text-muted-foreground">⚠</span>
                  )}
                  <span className="font-medium">&quot;{s.name}&quot;</span>
                  <AssessmentBadge assessment={s.assessment} />
                </div>
                <p className="mt-1 font-mono text-[13px] text-muted-foreground">
                  before: {s.before}
                </p>
                <p className="font-mono text-[13px] text-muted-foreground">
                  after: {s.after}
                </p>
                <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[13px] text-muted-foreground">
                  <Link href={`#run-${s.run_id}`} className="hover:underline">
                    run {s.run_id}
                  </Link>
                  <span>{s.scenario_id}</span>
                  {s.second_reviewer_required && (
                    <span
                      className={
                        s.second_reviewer_signed
                          ? "text-emerald-700 dark:text-emerald-300"
                          : "text-amber-800 dark:text-amber-200"
                      }
                    >
                      2nd reviewer{" "}
                      {s.second_reviewer_signed ? "signed" : "required"}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  )
}

function UnifiedDiff({ diff }: { diff: TextDiff }) {
  return (
    <pre className="overflow-x-auto rounded-md bg-muted/40 p-3 font-mono text-[13px] leading-5">
      <div className="text-muted-foreground">--- v{diff.from_version}</div>
      <div className="text-muted-foreground">+++ v{diff.to_version}</div>
      {diff.hunks.map((h) => (
        <div key={h.header}>
          <div className="text-sky-700 dark:text-sky-300">{h.header}</div>
          {h.lines.map((l, i) => (
            <div
              key={`${h.header}-${i}`}
              className={cn(
                l.op === "+" &&
                  "bg-emerald-500/10 text-emerald-900 dark:text-emerald-200",
                l.op === "-" && "bg-destructive/10 text-destructive",
              )}
            >
              {l.op}
              {l.text}
            </div>
          ))}
        </div>
      ))}
    </pre>
  )
}

function SplitDiff({ diff }: { diff: TextDiff }) {
  const left = diff.hunks.flatMap((h) => h.lines.filter((l) => l.op !== "+"))
  const right = diff.hunks.flatMap((h) => h.lines.filter((l) => l.op !== "-"))
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <pre className="overflow-x-auto rounded-md border p-3 font-mono text-[13px] leading-5">
        <div className="mb-1 text-muted-foreground">v{diff.from_version}</div>
        {left.map((l, i) => (
          <div
            key={i}
            className={cn(l.op === "-" && "bg-destructive/10 text-destructive")}
          >
            {l.text || " "}
          </div>
        ))}
      </pre>
      <pre className="overflow-x-auto rounded-md border p-3 font-mono text-[13px] leading-5">
        <div className="mb-1 text-muted-foreground">v{diff.to_version}</div>
        {right.map((l, i) => (
          <div
            key={i}
            className={cn(
              l.op === "+" &&
                "bg-emerald-500/10 text-emerald-900 dark:text-emerald-200",
            )}
          >
            {l.text || " "}
          </div>
        ))}
      </pre>
    </div>
  )
}
