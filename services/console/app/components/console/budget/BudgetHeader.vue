<script setup lang="ts">
import { ref } from "vue"
import { SlidersHorizontal } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import { BUDGET_WINDOWS, BUDGET_WINDOW_LABELS, type BudgetWindow } from "@/lib/budget-preview"

const props = defineProps<{ window: BudgetWindow }>()
const emit = defineEmits<{ "update:window": [value: BudgetWindow] }>()

const header = ref<InstanceType<typeof ConsolePageHeader> | null>(null)

const windowOptions = BUDGET_WINDOWS.map((value) => ({ value, label: BUDGET_WINDOW_LABELS[value] }))

const notes = [
  {
    lead: "Committed and held are different things.",
    body: "Committed is settled spend. Held is an in-flight reservation that has not settled yet, and it can still return to headroom. Only committed should be read as cost.",
  },
  {
    lead: "A ceiling only bites if enforcement says so.",
    body: "Hard ceilings make the runtime refuse work. Soft ceilings report an overage. Warn-only limits change nothing at runtime.",
  },
  {
    lead: "Nothing here is reconciled by default.",
    body: "Without an accounting watermark the console cannot say a figure is final, and it will not project an end-of-window number it cannot defend.",
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
    title="Budgets"
    definition="What each scope has already spent, what is still held in flight, and how much room is left before the runtime refuses work."
    state="illustrative"
    verdict="Every amount on this page is a recorded preview fixture. No accounting watermark is connected, so no figure here is final cost."
    contract="operator.budgets.reservations.v1 [NEEDS-BACKEND]"
    scope="org_demo_42 · 5 scopes"
    range="Recorded preview windows, 1–30 Oct 2026"
    coverage="Preview fixtures · no accounting watermark connected"
    :notes="notes"
  >
    <template #actions>
      <GovernFilterSelect
        label="Window"
        :model-value="props.window"
        :options="windowOptions"
        default-value="current"
        @update:model-value="emit('update:window', $event as BudgetWindow)"
      />
      <GovernLockedAction label="Change limit" :icon="SlidersHorizontal" />
    </template>
  </ConsolePageHeader>
</template>
