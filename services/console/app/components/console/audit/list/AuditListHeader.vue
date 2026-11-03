<script setup lang="ts">
import { Download } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import {
  AUDIT_RANGES,
  AUDIT_RANGE_LABELS,
  AUDIT_SAVED_VIEWS,
  type AuditRange,
  type AuditSavedViewId,
} from "@/lib/audit-preview"

const props = defineProps<{ range: AuditRange; view: AuditSavedViewId }>()

const emit = defineEmits<{
  "update:range": [range: AuditRange]
  "update:view": [view: AuditSavedViewId]
}>()

const rangeOptions = AUDIT_RANGES.map((range) => ({ value: range, label: AUDIT_RANGE_LABELS[range] }))
const viewOptions = AUDIT_SAVED_VIEWS.map((view) => ({ value: view.id, label: view.label }))

const aboutNotes = [
  {
    lead: "An event records one attempted change.",
    body: "Result says whether it was applied, rejected, retrying, or dead-lettered. Evidence says whether a producer record certifies the claim.",
  },
  {
    lead: "Idempotency is part of the record.",
    body: "Each event carries its key and how many effects and duplicates were observed, so an applied change can be shown to have happened exactly once.",
  },
  {
    lead: "The chain is not verified here.",
    body: "Until operator.audit.integrity.v1 is connected, the console makes no claim that the sequence has no gaps.",
  },
]
</script>

<template>
  <ConsolePageHeader
    title="Audit log"
    definition="Every change made in this workspace: who did it, what changed, and whether it was applied exactly once."
    state="illustrative"
    verdict="Every event, retry, and evidence mark on this page is a recorded preview fixture. No audit stream is connected, so this page cannot prove completeness."
    contract="operator.audit.list.v1 [NEEDS-BACKEND]"
    scope="org_demo_42 · workspace ws_42"
    range="Recorded preview events, 26–30 Oct 2026"
    coverage="Preview fixtures · no audit stream connected"
    :notes="aboutNotes"
  >
    <template #actions>
      <GovernFilterSelect
        label="Range"
        :model-value="props.range"
        :options="rangeOptions"
        default-value="7d"
        @update:model-value="emit('update:range', $event as AuditRange)"
      />
      <GovernFilterSelect
        label="View"
        :model-value="props.view"
        :options="viewOptions"
        default-value="all"
        @update:model-value="emit('update:view', $event as AuditSavedViewId)"
      />
      <GovernLockedAction label="Export" :icon="Download" />
    </template>
  </ConsolePageHeader>
</template>
