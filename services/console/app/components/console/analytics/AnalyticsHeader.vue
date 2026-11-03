<script setup lang="ts">
import { ref } from "vue"
import { Download } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import { ANALYTICS_RANGES, ANALYTICS_RANGE_LABELS, ANALYTICS_USAGE_CONTRACT, type AnalyticsRange } from "@/lib/analytics-preview"

const props = defineProps<{ range: AnalyticsRange }>()
const emit = defineEmits<{ "update:range": [value: AnalyticsRange] }>()

const header = ref<InstanceType<typeof ConsolePageHeader> | null>(null)

const rangeOptions = ANALYTICS_RANGES.map((range) => ({ value: range, label: ANALYTICS_RANGE_LABELS[range] }))

const notes = [
  {
    lead: "A trend is not a measurement.",
    body: "Series are fixture days with the shape of the projection they stand in for. They can show direction; they cannot be quoted as a usage figure.",
  },
  {
    lead: "Percentiles describe the newest recorded day.",
    body: "No measured window exists, so the latency band table reads one day and says so. p99 on this page is never comparable to a service objective.",
  },
  {
    lead: "Unrecorded days stay unrecorded.",
    body: "A wider range reports fewer recorded days rather than back-filling them. Absent is not the same as zero, and the page never draws a line between days it does not have.",
  },
]

function openAbout(): void {
  header.value?.openAbout()
}

defineExpose({ openAbout })
</script>

<template>
  <ConsolePageHeader
    ref="header"
    title="Analytics"
    definition="Volume, spend, latency and refusals across the recorded days — and how much of each number the platform can actually stand behind."
    state="illustrative"
    verdict="Every series, percentile, and split on this page is a derived preview fixture. The usage contract is not connected, so no figure here is billing or SLO evidence."
    :contract="ANALYTICS_USAGE_CONTRACT"
    scope="org_demo_42 · all producers"
    range="Recorded preview days, 17–30 Oct 2026"
    coverage="Preview fixtures · no usage contract connected"
    :notes="notes"
  >
    <template #actions>
      <GovernFilterSelect
        label="Range"
        :model-value="props.range"
        :options="rangeOptions"
        default-value="14d"
        @update:model-value="emit('update:range', $event as AnalyticsRange)"
      />
      <GovernLockedAction label="Export" :icon="Download" />
    </template>
  </ConsolePageHeader>
</template>
