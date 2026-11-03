<script setup lang="ts">
import { computed, ref } from "vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernPeekSheet from "@/components/console/govern/primitives/GovernPeekSheet.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import CompositionBar from "@/components/console/CompositionBar.vue"
import { formatGovernRelative, formatGovernStamp, GOVERN_NOW } from "@/lib/govern-format"
import {
  BUDGET_RESERVATIONS_CONTRACT,
  BUDGET_STATE_LABELS,
  BUDGET_WATERMARK_PENDING,
  ENFORCEMENT_LABELS,
  ENFORCEMENT_MEANING,
  budgetCommittedPercent,
  budgetHeadroomPercent,
  budgetHeadroomUsd,
  budgetReservedPercent,
  budgetState,
  budgetTotals,
  budgetUsd,
  lifecycleFor,
  type BudgetState,
  type Reservation,
} from "@/lib/budget-preview"

const props = defineProps<{ rows: Reservation[]; allRows: Reservation[] }>()

const STATE_BAR: Record<BudgetState, { committed: string; held: string; text: string }> = {
  ok: { committed: "bg-ok", held: "bg-warn", text: "text-ok" },
  tight: { committed: "bg-warn", held: "bg-crit", text: "text-warn" },
  exhausted: { committed: "bg-crit", held: "bg-crit", text: "text-crit" },
}

const totals = computed(() => budgetTotals(props.allRows))

const allocationSegments = computed(() => [
  { label: "Committed", value: totals.value.committed, color: "bg-s1" },
  { label: "Held", value: totals.value.reserved, color: "bg-s2" },
  { label: "Headroom", value: Math.max(0, totals.value.headroom), color: "bg-fg-off" },
])

const open = ref(false)
const selected = ref<Reservation | null>(null)

function peek(row: Reservation): void {
  selected.value = row
  open.value = true
}

const selectedEvents = computed(() => (selected.value ? lifecycleFor(selected.value.id) : []))
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <GovernStatTile
        label="Limit across scopes"
        :value="budgetUsd(totals.limit)"
        helper="Sum of the ceilings in force"
      />
      <GovernStatTile
        label="Committed"
        :value="budgetUsd(totals.committed)"
        helper="Settled spend only"
      />
      <GovernStatTile
        label="Held in flight"
        :value="budgetUsd(totals.reserved)"
        helper="May still return to headroom"
        tone="warning"
      />
      <GovernStatTile
        label="Headroom"
        :value="budgetUsd(totals.headroom)"
        :helper="`${totals.tight} close · ${totals.exhausted} at limit`"
      />
    </div>

    <div class="console-panel p-3">
      <CompositionBar title="Allocation across scopes" :segments="allocationSegments" height="md" />
    </div>

    <GovernCaveat tone="warning" title="Read committed, never committed plus held">
      {{ BUDGET_WATERMARK_PENDING }} A hold that has not settled is not money spent; releasing it returns the room.
    </GovernCaveat>

    <div v-if="rows.length === 0" class="rounded-lg border border-line-subtle bg-surface-1 p-2">
      <GovernEmptyState
        title="No reservations match these filters"
        reason="No scope in this window has the selected kind, enforcement, or search term."
        next-step="Clear the filters, or switch to the previous billing window."
      />
    </div>

    <div v-else class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
      <table class="ix-agent-table table-fixed" style="min-width: 1070px" aria-label="Budget reservations">
        <thead>
          <tr>
            <th scope="col" style="width: 220px">Scope</th>
            <th scope="col" style="width: 120px">Enforcement</th>
            <th scope="col" style="width: 100px" class="text-right">Limit</th>
            <th scope="col" style="width: 110px" class="text-right">Committed</th>
            <th scope="col" style="width: 100px" class="text-right">Held</th>
            <th scope="col" style="width: 190px">Used</th>
            <th scope="col" style="width: 110px" class="text-right">Headroom</th>
            <th scope="col" style="width: 120px">Reconciled</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            tabindex="0"
            class="cursor-pointer"
            @click="peek(row)"
            @keydown.enter.prevent="peek(row)"
            @keydown.space.prevent="peek(row)"
          >
            <td>
              <p class="truncate text-xs font-medium text-fg-1" :title="row.label">{{ row.label }}</p>
              <p class="mt-0.5 truncate font-mono text-[0.625rem] leading-4 text-fg-3" :title="row.scopeId">
                {{ row.scopeId }} · {{ row.id }}
              </p>
            </td>
            <td>
              <span class="text-xs text-fg-2" :title="ENFORCEMENT_MEANING[row.enforcement]">{{ ENFORCEMENT_LABELS[row.enforcement] }}</span>
            </td>
            <td class="text-right font-mono text-xs text-fg-2 tabular-nums">{{ budgetUsd(row.limitUsd) }}</td>
            <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ budgetUsd(row.committedUsd) }}</td>
            <td class="text-right font-mono text-xs tabular-nums" :class="row.reservedUsd > 0 ? 'text-warn' : 'text-fg-3'">
              {{ row.reservedUsd > 0 ? budgetUsd(row.reservedUsd) : "—" }}
            </td>
            <td>
              <span class="flex h-2 w-full overflow-hidden rounded-full bg-surface-2" role="img" :aria-label="`${BUDGET_STATE_LABELS[budgetState(row)]}: ${budgetCommittedPercent(row).toFixed(0)}% committed, ${budgetReservedPercent(row).toFixed(0)}% held`">
                <span :style="{ width: `${budgetCommittedPercent(row)}%` }" :class="STATE_BAR[budgetState(row)].committed" />
                <span :style="{ width: `${budgetReservedPercent(row)}%` }" :class="STATE_BAR[budgetState(row)].held" />
              </span>
              <span class="mt-1 block text-[0.625rem] leading-4" :class="STATE_BAR[budgetState(row)].text">
                {{ BUDGET_STATE_LABELS[budgetState(row)] }}
              </span>
            </td>
            <td class="text-right font-mono text-xs text-fg-2 tabular-nums">
              {{ budgetUsd(budgetHeadroomUsd(row)) }}
              <span class="block text-[0.625rem] leading-4 text-fg-3">{{ budgetHeadroomPercent(row).toFixed(0) }}% left</span>
            </td>
            <td>
              <span v-if="row.watermarkAt" class="font-mono text-[0.6875rem] whitespace-nowrap text-fg-2" :title="formatGovernStamp(row.watermarkAt)">
                {{ formatGovernRelative(row.watermarkAt, GOVERN_NOW) }}
              </span>
              <span v-else class="text-xs text-warn" :title="BUDGET_WATERMARK_PENDING">Never</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <GovernPendingData
      title="Projected end-of-window spend"
      :contract="BUDGET_RESERVATIONS_CONTRACT"
      description="A projection needs a certified watermark and the run history behind it. Neither is connected, so this page reports what is committed and held and stops there."
    />

    <GovernPeekSheet
      v-if="selected"
      v-model:open="open"
      :title="selected.label"
      :description="`${ENFORCEMENT_LABELS[selected.enforcement]} · ${budgetUsd(selected.committedUsd)} of ${budgetUsd(selected.limitUsd)}`"
    >
      <div class="flex flex-col gap-3">
        <div class="rounded-lg border border-line-subtle bg-surface-2 px-3 py-2.5">
          <p class="text-xs font-medium" :class="STATE_BAR[budgetState(selected)].text">
            {{ BUDGET_STATE_LABELS[budgetState(selected)] }} · {{ budgetUsd(budgetHeadroomUsd(selected)) }} headroom
          </p>
          <p class="mt-0.5 text-xs leading-4 text-fg-3">{{ ENFORCEMENT_MEANING[selected.enforcement] }}</p>
        </div>

        <dl class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle">
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Committed</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1 tabular-nums">{{ budgetUsd(selected.committedUsd) }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Held</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1 tabular-nums">
              {{ selected.reservedUsd > 0 ? budgetUsd(selected.reservedUsd) : "None" }}
            </dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Window</dt>
            <dd class="mt-0.5 text-xs text-fg-2">
              {{ formatGovernRelative(selected.windowStart, GOVERN_NOW) }} → {{ formatGovernRelative(selected.windowEnd, GOVERN_NOW) }}
            </dd>
          </div>
          <div class="bg-surface-1 px-3 py-2">
            <dt class="text-[0.6875rem] text-fg-3">Last hold</dt>
            <dd class="mt-0.5 font-mono text-[0.6875rem] text-fg-2">
              {{ selected.lastReservationAt ? formatGovernRelative(selected.lastReservationAt, GOVERN_NOW) : "Not recorded" }}
            </dd>
          </div>
        </dl>

        <div>
          <p class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Recorded lifecycle</p>
          <ol v-if="selectedEvents.length" class="mt-1.5 flex flex-col gap-1.5">
            <li v-for="event in selectedEvents" :key="event.id" class="text-xs leading-5 text-fg-2">
              <span class="font-mono text-[0.6875rem] text-fg-3">{{ formatGovernRelative(event.at, GOVERN_NOW) }}</span>
              · {{ event.detail }}
            </li>
          </ol>
          <p v-else class="mt-1.5 text-xs text-fg-3">No lifecycle rows recorded for this scope.</p>
        </div>

        <p v-if="selected.note" class="text-[0.6875rem] leading-4 text-fg-3">{{ selected.note }}</p>

        <NuxtLink to="/budgets?tab=lifecycle" class="ix-button-secondary h-8 w-fit px-3 text-xs">
          Open the lifecycle tab
        </NuxtLink>
      </div>
    </GovernPeekSheet>
  </div>
</template>
