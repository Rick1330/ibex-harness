<script setup lang="ts">
import { ref } from "vue"
import { Download } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import { EVIDENCE_RANGES, EVIDENCE_RANGE_LABELS, EVIDENCE_SUMMARY_CONTRACT, type EvidenceRange } from "@/lib/evidence-preview"

const props = defineProps<{ range: EvidenceRange }>()
const emit = defineEmits<{ "update:range": [value: EvidenceRange] }>()

const header = ref<InstanceType<typeof ConsolePageHeader> | null>(null)

const rangeOptions = EVIDENCE_RANGES.map((range) => ({ value: range, label: EVIDENCE_RANGE_LABELS[range] }))

const notes = [
  {
    lead: "A tier describes what can be re-proved.",
    body: "Evidence means the record can be re-read by digest. Metadata means only the envelope is certified. Uncertified means it was observed with nothing behind it. Unavailable means publication failed; it is never estimated.",
  },
  {
    lead: "Derived rows are not proof.",
    body: "ClickHouse projections are counted as uncertified on purpose. A billing or deletion claim has to point at an evidence record, not at a projection.",
  },
  {
    lead: "Chain gaps come from the local sequence.",
    body: "Until operator.evidence.summary.v1 is connected, a gap means a sequence number has no outbox row here — not that an external verifier confirmed the chain.",
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
    title="Evidence"
    definition="Which records can still be re-proved, what was deleted and under what basis, and where the chain to analytics breaks."
    state="illustrative"
    verdict="Every count, tombstone, and chain row on this page is a recorded preview fixture. The evidence summary is not connected, so nothing here certifies completeness."
    :contract="EVIDENCE_SUMMARY_CONTRACT"
    scope="org_demo_42 · 6 producers"
    range="Recorded preview fixtures, 28–30 Oct 2026"
    coverage="Preview fixtures · no evidence summary connected"
    :notes="notes"
  >
    <template #actions>
      <GovernFilterSelect
        label="Range"
        :model-value="props.range"
        :options="rangeOptions"
        default-value="24h"
        @update:model-value="emit('update:range', $event as EvidenceRange)"
      />
      <GovernLockedAction label="Export" :icon="Download" />
    </template>
  </ConsolePageHeader>
</template>
