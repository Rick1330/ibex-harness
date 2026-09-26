"use client"

import { IconLock } from "@tabler/icons-react"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { PrivilegedActionButton } from "@/components/sessions/privileged-gate"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { ReplaySandboxState } from "@/lib/sessions/types"

export function ReplaySandbox({ state }: { state: ReplaySandboxState }) {
  return (
    <Card id="replay" className={panelClass}>
      <CardHeader className="gap-2 border-b border-amber-600/30 bg-amber-500/5 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md border border-amber-600/40 bg-background px-2 py-0.5 font-mono text-[13px] text-amber-900 dark:text-amber-200">
            <IconLock className="size-3.5" />
            SANDBOX — no production effects
          </span>
        </div>
        <CardTitle className="text-[13px] font-medium leading-5">
          Replaying from snapshot @ {state.snapshot_at} (frozen)
        </CardTitle>
        <p className="font-mono text-[13px] text-muted-foreground">
          directive v{state.directive_version} ({state.directive_hash}) · model{" "}
          {state.model_version} · tokenizer {state.tokenizer_version} · packer{" "}
          {state.packing_policy_version}
        </p>
        <p className="text-[13px] leading-5 text-muted-foreground">
          No memory writes, no secret access, no external calls in replay. Not
          ordinary idempotency replay — sandboxed reconstruction only.
        </p>
      </CardHeader>
      <CardContent className="space-y-3 px-4 py-3 text-[13px] leading-5">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-md border p-3">
            <div className="mb-2 text-[13px] font-medium text-muted-foreground">
              Original
            </div>
            <p className="font-mono text-[13px]">
              tool: {state.original.tool} → {state.original.tool_result}
            </p>
            <p className="mt-1 font-mono text-[13px] text-muted-foreground">
              response: {state.original.tokens}tk · {state.original.latency_ms}
              ms
            </p>
          </div>
          <div className="rounded-md border border-dashed p-3">
            <div className="mb-2 text-[13px] font-medium text-muted-foreground">
              Replayed
            </div>
            <p className="font-mono text-[13px]">
              tool: {state.replayed.tool}{" "}
              {state.replayed.mocked ? "[MOCKED]" : ""} →{" "}
              {state.replayed.tool_result}
            </p>
            <p className="mt-1 font-mono text-[13px] text-muted-foreground">
              response: {state.replayed.tokens}tk · {state.replayed.latency_ms}
              ms
            </p>
          </div>
        </div>

        <p className="font-mono text-[13px]">
          Diff: {state.diff.tokens_delta} tokens · {state.diff.latency_delta_ms}
          ms · {state.diff.summary}
        </p>
        <p className="font-mono text-[13px] text-muted-foreground">
          Audit: {state.audit_request_id} (separate from original{" "}
          {state.original_request_id})
        </p>

        <div className="flex flex-wrap gap-2 pt-1">
          <PrivilegedActionButton>
            Preview → Approve replay
          </PrivilegedActionButton>
        </div>
      </CardContent>
    </Card>
  )
}
