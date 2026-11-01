<script setup lang="ts">
import { computed } from "vue"
import { CircleDashed } from "@lucide/vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import { formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import {
  BUDGET_RESERVATIONS_CONTRACT,
  RESERVATION_EVENT_LABELS,
  RESERVATION_EVENT_MEANING,
  budgetUsd,
  lifecycleCounts,
  reservationById,
  type ReservationEvent,
  type ReservationEventType,
} from "@/lib/budget-preview"
import { auditEventHref } from "@/lib/govern-query"

const props = defineProps<{ rows: ReservationEvent[]; allRows: ReservationEvent[] }>()

const TYPE_CLASS: Record<ReservationEventType, string> = {
  created: "text-fg-2 border-line-subtle bg-surface-1",
  reserved: "text-warn border-warn/30 bg-warn-tint",
  committed: "text-ok border-ok/30 bg-ok-tint",
  released: "text-fg-2 border-line-subtle bg-surface-1",
  expired: "text-warn border-warn/30 bg-warn-tint",
  denied: "text-crit border-crit/30 bg-crit-tint",
}

const RAIL_CLASS: Record<ReservationEventType, string> = {
  created: "bg-fg-3",
  reserved: "bg-warn",
  committed: "bg-ok",
  released: "bg-fg-3",
  expired: "bg-warn",
  denied: "bg-crit",
}

const counts = computed(() => lifecycleCounts(props.allRows))

const days = computed(() => {
  const groups: { key: string; label: string; events: ReservationEvent[] }[] = []
  const ordered = [...props.rows].sort((left, right) => Date.parse(right.at) - Date.parse(left.at))
  for (const event of ordered) {
    const stamp = formatGovernStamp(event.at)
    const label = stamp.split(",")[0] ?? stamp
    const existing = groups.find((group) => group.key === label)
    if (existing) existing.events.push(event)
    else groups.push({ key: label, label, events: [event] })
  }
  return groups
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center gap-2" aria-label="Reservation lifecycle counts">
      <span class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">This window</span>
      <span class="inline-flex items-center gap-2 rounded-full border border-line-subtle bg-surface-1 px-2.5 py-1 text-xs text-fg-2">
        <span class="font-mono text-sm leading-5 font-semibold tabular-nums text-warn">{{ counts.open }}</span> holds open
      </span>
      <span class="inline-flex items-center gap-2 rounded-full border border-line-subtle bg-surface-1 px-2.5 py-1 text-xs text-fg-2">
        <span class="font-mono text-sm leading-5 font-semibold tabular-nums text-warn">{{ counts.expired }}</span> expired
      </span>
      <span class="inline-flex items-center gap-2 rounded-full border border-line-subtle bg-surface-1 px-2.5 py-1 text-xs text-fg-2">
        <span class="font-mono text-sm leading-5 font-semibold tabular-nums text-crit">{{ counts.denied }}</span> runs refused
      </span>
    </div>

    <GovernCaveat tone="info" title="Why the lifecycle is separate from the audit log">
      A reservation moves through holds that never become money. The audit log records the mutation; this view records
      the money state, including the releases and expiries that left no trace in committed spend.
    </GovernCaveat>

    <div v-if="rows.length === 0" class="rounded-lg border border-line-subtle bg-surface-1 p-2">
      <GovernEmptyState
        title="No lifecycle rows in this view"
        reason="No recorded reservation event matches the current scope filter or search."
        next-step="Clear the filters to see every event in the window."
      />
    </div>

    <div v-else class="flex flex-col gap-3">
      <section v-for="group in days" :key="group.key" class="flex flex-col gap-2">
        <h2 class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">
          {{ group.label }} · {{ group.events.length }} event{{ group.events.length === 1 ? "" : "s" }}
        </h2>
        <ol class="flex flex-col gap-2">
          <li
            v-for="event in group.events"
            :key="event.id"
            class="relative rounded-lg border border-line-subtle bg-surface-1 py-3 pr-3.5 pl-5"
          >
            <span class="absolute inset-y-0 left-0 w-1 rounded-l" :class="RAIL_CLASS[event.type]" aria-hidden="true" />

            <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span
                class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-xs leading-none font-medium whitespace-nowrap"
                :class="TYPE_CLASS[event.type]"
                :title="RESERVATION_EVENT_MEANING[event.type]"
              >
                {{ RESERVATION_EVENT_LABELS[event.type] }}
              </span>
              <span class="text-xs font-medium text-fg-1">{{ event.scopeLabel }}</span>
              <span v-if="event.amountUsd !== null" class="font-mono text-xs text-fg-2 tabular-nums">
                {{ budgetUsd(event.amountUsd) }}
              </span>
              <span class="ml-auto font-mono text-[0.6875rem] whitespace-nowrap text-fg-3" :title="formatGovernStamp(event.at)">
                {{ formatGovernRelative(event.at) }}
              </span>
            </div>

            <p class="mt-1.5 text-xs leading-5 text-fg-2">{{ event.detail }}</p>

            <div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.6875rem] text-fg-3">
              <span>{{ event.actor }}</span>
              <span v-if="reservationById(event.reservationId)" class="font-mono">
                {{ reservationById(event.reservationId)?.id }}
              </span>
              <NuxtLink
                v-if="event.auditEventId"
                :to="auditEventHref(event.auditEventId)"
                class="inline-flex items-center gap-1 underline decoration-line-strong underline-offset-2 hover:text-fg-1"
              >
                <CircleDashed :size="11" :stroke-width="1.8" aria-hidden="true" />
                See the audit event
              </NuxtLink>
            </div>
          </li>
        </ol>
      </section>
    </div>

    <GovernPendingData
      title="Reconciliation runs"
      :contract="BUDGET_RESERVATIONS_CONTRACT"
      description="When committed spend was last checked against accounting is a watermark question. Until it is connected, this page shows holds and settlements only."
    />
  </div>
</template>
