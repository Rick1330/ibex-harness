<script setup lang="ts">
import type { PublicOperatorContext } from "~~/shared/operator/public"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import OverviewStreamPanel from "./OverviewStreamPanel.vue"
import { formatGovernStamp } from "@/lib/govern-format"
import { formatLiveRelative } from "@/lib/live-format"
import { OVERVIEW_SOURCE_STATE_LABELS, type OverviewSourceRow } from "@/lib/overview-view"

const props = defineProps<{
  sources: OverviewSourceRow[]
  context: PublicOperatorContext | null
  nowMs: number | null
  streamEnabled: boolean
}>()

const STATE_CLASS: Record<OverviewSourceRow["state"], string> = {
  ok: "text-ok",
  degraded: "text-warn",
  missing: "text-crit",
  pending: "text-fg-3",
}

function roleLabel(role: string | null): string {
  if (!role) return "Not reported by the session"
  return role.charAt(0).toUpperCase() + role.slice(1)
}
</script>

<template>
  <section class="flex min-w-0 flex-col gap-3" aria-label="Sources and session">
    <div class="ix-scroll min-w-0 overflow-x-auto rounded-lg border border-line-subtle">
      <table class="ix-agent-table table-fixed" style="min-width: 860px" aria-label="What this page read">
        <thead>
          <tr>
            <th scope="col" style="width: 170px">Source</th>
            <th scope="col" style="width: 230px">Contract</th>
            <th scope="col" style="width: 90px">State</th>
            <th scope="col" style="width: 150px">Observed</th>
            <th scope="col" style="width: 220px">What it powers here</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="source in props.sources" :key="source.id" class="align-top">
            <td>
              <p class="truncate text-xs font-medium text-fg-1">{{ source.label }}</p>
              <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">{{ source.detail }}</p>
            </td>
            <td>
              <span class="flex items-center gap-1">
                <code class="truncate font-mono text-[0.6875rem] text-fg-2" :title="source.contract">{{ source.contract }}</code>
                <GovernCopyId :id="source.contract" :label="`${source.label} contract`" icon-only truncate />
              </span>
            </td>
            <td>
              <span class="text-xs" :class="STATE_CLASS[source.state]">{{ OVERVIEW_SOURCE_STATE_LABELS[source.state] }}</span>
            </td>
            <td class="font-mono text-[0.6875rem] leading-4 whitespace-nowrap text-fg-2">
              <span v-if="source.observedAt" :title="formatGovernStamp(source.observedAt)">
                {{ formatLiveRelative(source.observedAt, props.nowMs) }}
              </span>
              <span v-else class="text-fg-3">Not read</span>
            </td>
            <td class="text-[0.6875rem] leading-4 text-fg-3">{{ source.feeds }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="grid gap-3 lg:grid-cols-2">
      <div class="rounded-lg border border-line-subtle bg-surface px-3.5 py-3">
        <h3 class="text-xs font-medium text-fg-1">This session</h3>
        <dl class="mt-2 space-y-2 text-xs">
          <div class="flex items-baseline justify-between gap-3">
            <dt class="text-fg-3">Role</dt>
            <dd class="text-fg-1">{{ roleLabel(props.context?.role ?? null) }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3">
            <dt class="text-fg-3">Organization</dt>
            <dd class="min-w-0 truncate text-right text-fg-1" :title="props.context?.org_name">{{ props.context?.org_name ?? "Not reported" }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3">
            <dt class="text-fg-3">Slug</dt>
            <dd class="font-mono text-[0.6875rem] text-fg-2">{{ props.context?.org_slug ?? "Not reported" }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3">
            <dt class="text-fg-3">Organization status</dt>
            <dd class="text-fg-1">{{ props.context?.org_status ?? "Not reported" }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3">
            <dt class="text-fg-3">Session verified</dt>
            <dd class="font-mono text-[0.6875rem] whitespace-nowrap text-fg-2">{{ formatGovernStamp(props.context?.observed_at ?? null) }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3">
            <dt class="text-fg-3">Mode</dt>
            <dd class="text-fg-1">Read-only</dd>
          </div>
        </dl>
        <GovernCaveat class="mt-2.5" tone="info" title="Shown exactly as reported">
          <code class="font-mono">org_status</code> is a free-form string on operator.context.v1. The console has no
          recorded vocabulary for it, so it is printed as received and never coloured, mapped, or turned into a verdict.
        </GovernCaveat>
      </div>

      <div class="flex min-w-0 flex-col gap-3">
        <div class="rounded-lg border border-line-subtle bg-surface px-3.5 py-3">
          <h3 class="text-xs font-medium text-fg-1">Evidence coverage</h3>
          <GovernPendingData
            class="mt-2"
            title="Certification coverage"
            contract="operator.evidence.summary.v1"
            description="Health is not certification. A dependency reporting ok cannot be read as evidence coverage, so this page leaves the figure unreported."
          />
        </div>
        <OverviewStreamPanel :enabled="props.streamEnabled" :now-ms="props.nowMs" />
      </div>
    </div>
  </section>
</template>
