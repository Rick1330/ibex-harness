"use client"

import * as React from "react"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { ActionLedger } from "@/components/directives/action-ledger"
import { DiffViewer } from "@/components/directives/diff-viewer"
import { ExperimentPanel } from "@/components/directives/experiment-panel"
import { PromotionConsole } from "@/components/directives/promotion-console"
import { RoutingProvenancePanel } from "@/components/directives/routing-provenance"
import {
  LifecycleBadge,
  RegressionBadge,
  RolloutStageChip,
} from "@/components/directives/status-badges"
import { VersionTimeline } from "@/components/directives/version-timeline"
import { CopyId } from "@/components/explore/copy-id"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type {
  ActionLedgerEntry,
  DirectiveDetail,
  ExperimentState,
  RolloutState,
} from "@/lib/directives/types"
import { CONTROLLED_ACTIONS_ENABLED } from "@/lib/directives/types"

export function DirectiveDetailView({
  directive: initial,
}: {
  directive: DirectiveDetail
}) {
  const [selectedVersion, setSelectedVersion] = React.useState(
    initial.versions[0]?.version ?? 1,
  )
  const [diffMode, setDiffMode] = React.useState<"unified" | "split">("unified")
  const [ledger, setLedger] = React.useState<ActionLedgerEntry[]>(
    initial.ledger,
  )
  const [rollout, setRollout] = React.useState<RolloutState | null>(
    initial.rollout_live,
  )
  const [experiment, setExperiment] = React.useState<ExperimentState | null>(
    initial.experiment,
  )

  const appendLedger = (entry: ActionLedgerEntry) => {
    setLedger((prev) => {
      if (prev.some((e) => e.idempotency_key === entry.idempotency_key)) {
        return prev
      }
      return [entry, ...prev]
    })
  }

  const baseline =
    initial.versions.find((v) => v.version !== selectedVersion)?.version ??
    selectedVersion - 1

  return (
    <div className="space-y-3">
      {!CONTROLLED_ACTIONS_ENABLED && (
        <p className="rounded-md border border-amber-600/30 bg-amber-500/5 px-3 py-2 text-[13px] leading-5 text-amber-900 dark:text-amber-200">
          Controlled actions disabled (rollback). Prior policy remains active;
          preview/approval fail closed until restored.
        </p>
      )}

      <Card className={panelClass}>
        <CardHeader className="gap-2 border-b px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <CopyId
              value={initial.directive_id}
              label="directive_id"
              className="font-mono text-[13px] font-medium"
            />
            <LifecycleBadge status={initial.status} />
            <RegressionBadge
              status={initial.regression_status}
              passed={initial.scenarios_passed}
              total={initial.scenarios_total}
            />
            {initial.rollout && (
              <RolloutStageChip
                stage={initial.rollout.stage}
                percentage={initial.rollout.percentage}
              />
            )}
          </div>
          <CardTitle className="text-[13px] font-medium">
            {initial.name}{" "}
            <span className="font-normal text-muted-foreground">
              · {initial.agent}
            </span>
          </CardTitle>
          <p className="text-[13px] leading-5 text-muted-foreground">
            {initial.description}
          </p>
          <p className="font-mono text-[13px] text-muted-foreground">
            owner {initial.owner}
            {initial.last_promoted_by
              ? ` · last promoted by ${initial.last_promoted_by} @ ${initial.last_promoted_at?.slice(0, 10)}`
              : " · never promoted"}
          </p>
        </CardHeader>
      </Card>

      <div className="grid items-start gap-3 lg:grid-cols-[minmax(240px,0.35fr)_minmax(0,1fr)]">
        <Card className={panelClass}>
          <CardHeader className="gap-1 border-b px-4 py-3">
            <CardTitle className="text-[13px] font-medium">
              Version timeline
            </CardTitle>
            <p className="text-[13px] text-muted-foreground">
              Content, content_hash, and content_tokens are immutable after
              create — only status transitions.
            </p>
          </CardHeader>
          <CardContent className="px-4 py-3">
            <VersionTimeline
              versions={initial.versions}
              selected={selectedVersion}
              onSelect={setSelectedVersion}
            />
          </CardContent>
        </Card>

        <DiffViewer
          diff={initial.diff}
          behavioral={initial.behavioral}
          mode={diffMode}
          onModeChange={setDiffMode}
        />
      </div>

      <PromotionConsole
        targetVersion={selectedVersion}
        baselineVersion={baseline > 0 ? baseline : 1}
        blockedReason={initial.promote_blocked_reason}
        blast={initial.blast_radius}
        rollout={rollout}
        onLedger={appendLedger}
        onRolloutChange={setRollout}
      />

      <div className="grid items-start gap-3 lg:grid-cols-2">
        <RoutingProvenancePanel routing={initial.routing_sample} />
        {experiment ? (
          <ExperimentPanel
            experiment={experiment}
            onChange={setExperiment}
            onLedger={appendLedger}
          />
        ) : (
          <Card className={panelClass}>
            <CardContent className="px-4 py-6 text-[13px] text-muted-foreground">
              No active experiment on this directive.
            </CardContent>
          </Card>
        )}
      </div>

      <ActionLedger entries={ledger} />
    </div>
  )
}
