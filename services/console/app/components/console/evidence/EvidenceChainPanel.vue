<script setup lang="ts">
import { ArrowRight, CircleSlash, Clock, Link2, ShieldAlert } from "@lucide/vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernIdChip from "@/components/console/govern/primitives/GovernIdChip.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import { formatGovernRelative, formatGovernStamp, formatGovernStampSeconds } from "@/lib/govern-format"
import {
  CHAIN_STATE_LABELS,
  EVIDENCE_SUMMARY_CONTRACT,
  chainLagText,
  type ChainLink,
  type ChainState,
} from "@/lib/evidence-preview"

defineProps<{ rows: ChainLink[]; counts: Record<ChainState, number> }>()

const RAIL_CLASS: Record<ChainState, string> = {
  delivered: "bg-ok",
  pending: "bg-warn",
  retrying: "bg-warn",
  poison: "bg-crit",
  gap: "bg-crit",
}

const TEXT_CLASS: Record<ChainState, string> = {
  delivered: "text-ok",
  pending: "text-warn",
  retrying: "text-warn",
  poison: "text-crit",
  gap: "text-crit",
}

const STATE_ICON: Record<ChainState, unknown> = {
  delivered: Link2,
  pending: Clock,
  retrying: Clock,
  poison: CircleSlash,
  gap: ShieldAlert,
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <GovernCaveat tone="info" title="How a gap is detected here">
      Sequence numbers are read from the local outbox only. A gap means no row exists here for that number — it is not a
      verified statement that the event never happened, and nothing downstream is polled to find out.
    </GovernCaveat>

    <div class="flex flex-wrap items-center gap-2" aria-label="Chain state counts">
      <span
        v-for="state in (['delivered', 'pending', 'retrying', 'poison', 'gap'] as ChainState[])"
        :key="state"
        class="inline-flex items-center gap-1.5 rounded-full border border-line-subtle bg-surface-1 px-2.5 py-1 text-xs text-fg-2"
      >
        <span class="size-2 rounded-full" :class="RAIL_CLASS[state]" aria-hidden="true" />
        <span class="font-mono text-sm leading-5 font-semibold tabular-nums" :class="TEXT_CLASS[state]">{{ counts[state] }}</span>
        {{ CHAIN_STATE_LABELS[state] }}
      </span>
    </div>

    <div v-if="rows.length === 0" class="rounded-lg border border-line-subtle bg-surface-1 p-2">
      <GovernEmptyState
        title="No outbox rows in this view"
        reason="No recorded chain row matches the current state filter or search."
        next-step="Clear the state filter, or widen the range."
      />
    </div>

    <ol v-else class="flex flex-col gap-2">
      <li
        v-for="link in rows"
        :key="`${link.seq}-${link.outboxId ?? 'gap'}`"
        class="relative overflow-hidden rounded-lg border border-line-subtle bg-surface-1 py-3 pr-3.5 pl-5"
      >
        <span class="absolute inset-y-0 left-0 w-1" :class="RAIL_CLASS[link.state]" aria-hidden="true" />

        <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
          <component :is="STATE_ICON[link.state]" :size="13" :stroke-width="1.9" :class="TEXT_CLASS[link.state]" aria-hidden="true" />
          <span class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">#{{ link.seq }}</span>
          <GovernIdChip v-if="link.outboxId" :value="link.outboxId" label="Outbox row" />
          <span v-else class="font-mono text-[0.6875rem] text-crit">no outbox row</span>
          <span class="ml-auto text-[0.6875rem] font-medium" :class="TEXT_CLASS[link.state]">
            {{ CHAIN_STATE_LABELS[link.state] }}
          </span>
        </div>

        <p class="mt-1.5 flex flex-wrap items-center gap-x-1.5 text-xs text-fg-1">
          <span class="font-mono text-[0.6875rem] text-fg-2">{{ link.producer }}</span>
          <ArrowRight v-if="link.producer !== link.consumer" :size="12" :stroke-width="1.9" class="text-fg-3" aria-hidden="true" />
          <span class="font-mono text-[0.6875rem] text-fg-2">{{ link.consumer }}</span>
          <span class="text-fg-3">·</span>
          <span class="font-mono text-[0.6875rem] text-fg-2">{{ link.kind }}</span>
        </p>

        <p class="mt-1 text-xs leading-5 text-fg-2">{{ link.detail }}</p>

        <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.6875rem] text-fg-3">
          <span class="font-mono whitespace-nowrap" :title="formatGovernStampSeconds(link.enqueuedAt)">
            Enqueued {{ formatGovernRelative(link.enqueuedAt) }}
          </span>
          <span v-if="link.settledAt" class="font-mono whitespace-nowrap" :title="formatGovernStamp(link.settledAt)">
            Settled {{ formatGovernRelative(link.settledAt) }}
          </span>
          <span v-else class="whitespace-nowrap">Not settled</span>
          <span>{{ link.attempts }} attempt{{ link.attempts === 1 ? "" : "s" }}</span>
          <span>Lag {{ chainLagText(link) }}</span>
          <GovernCopyId v-if="link.outboxId" :id="link.outboxId" label="Outbox row" icon-only />
        </div>
      </li>
    </ol>

    <GovernPendingData
      title="Chain verification"
      :contract="EVIDENCE_SUMMARY_CONTRACT"
      description="Whether every producer write reached every consumer is an evidence-summary question. Until it is connected, this page reports the local sequence only and makes no completeness claim."
    />
  </div>
</template>
