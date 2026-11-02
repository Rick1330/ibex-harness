<script setup lang="ts">
import { computed } from "vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import { formatGovernNumber, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import {
  DELIVERY_LABELS,
  DELIVERY_MEANING,
  DELIVERY_ORDER,
  DELIVERY_TONE,
  deliveryTotal,
  unsettledDelivery,
  type OperatorEvidenceSummary,
} from "@/lib/evidence-summary"

const props = defineProps<{ summary: OperatorEvidenceSummary }>()

const total = computed(() => deliveryTotal(props.summary.delivery))
const unsettled = computed(() => unsettledDelivery(props.summary.delivery))
// The relay retries `failed` after backoff; only `poison` stops being claimed.
const needingAttention = computed(() => props.summary.delivery.poison)
const retrying = computed(() => props.summary.delivery.failed)
const oldest = computed(() => props.summary.oldest_unsettled_at)
const reference = computed(() => props.summary.observed_at)
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
      <GovernStatTile
        label="Events in window"
        :value="formatGovernNumber(total)"
        helper="Outbox rows created in this range"
      />
      <GovernStatTile
        label="Delivered"
        :value="formatGovernNumber(summary.delivery.delivered)"
        :helper="summary.last_delivered_at ? `Last ${formatGovernRelative(summary.last_delivered_at, reference)}` : 'Nothing delivered in range'"
        tone="success"
      />
      <GovernStatTile
        label="Unsettled"
        :value="formatGovernNumber(unsettled)"
        helper="Pending, in flight, failed, or poison"
        :tone="unsettled > 0 ? 'warning' : 'default'"
      />
      <GovernStatTile
        label="Poisoned"
        :value="formatGovernNumber(needingAttention)"
        helper="Stopped being claimed: needs an operator decision"
        :tone="needingAttention > 0 ? 'critical' : 'default'"
      />
    </div>

    <div class="console-panel p-3">
      <ul class="flex flex-col gap-1 text-[0.6875rem] leading-4 text-fg-3">
        <li v-for="key in DELIVERY_ORDER" :key="key" class="flex flex-wrap items-baseline gap-x-2">
          <span class="w-20 shrink-0 font-medium text-fg-2" :class="{ 'text-crit': DELIVERY_TONE[key] === 'critical' }">
            {{ DELIVERY_LABELS[key] }}
          </span>
          <span class="font-mono tabular-nums text-fg-1">{{ formatGovernNumber(summary.delivery[key]) }}</span>
          <span class="min-w-0 flex-1">{{ DELIVERY_MEANING[key] }}</span>
        </li>
      </ul>
      <p class="mt-2 text-[0.6875rem] leading-4 text-fg-3">
        <span v-if="oldest">
          Oldest unsettled row {{ formatGovernRelative(oldest, reference) }} ({{ formatGovernStamp(oldest) }}).
        </span>
        <span v-else-if="unsettled === 0">Every row in the window is settled.</span>
        <span v-else>No undelivered row has a timestamp yet; the unsettled count above is not zero.</span>
        <span v-if="retrying > 0">
          {{ formatGovernNumber(retrying) }} failed row(s) are retried by the relay after backoff.
        </span>
      </p>
    </div>

    <GovernCaveat tone="info" title="Why this is an organization-level figure">
      The outbox does not carry a run reference, so delivery cannot be attributed to an individual evidence run. A
      complete capture with an unsettled outbox is a record that exists but has not reached its sink — both facts are
      shown rather than folded into one verdict.
    </GovernCaveat>
  </div>
</template>
