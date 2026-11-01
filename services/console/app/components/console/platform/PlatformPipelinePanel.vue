<script setup lang="ts">
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import { PLATFORM_CONTRACT, type PlatformField } from "@/lib/platform-view"

const props = defineProps<{
  fields: PlatformField[]
  resolved: boolean
}>()

const VALUE_CLASS = {
  default: "text-fg-1",
  warning: "text-warn",
  muted: "text-fg-3",
} as const
</script>

<template>
  <section class="flex min-w-0 flex-col gap-3" aria-label="Ingestion and outbox">
    <div class="divide-y divide-line-subtle rounded-lg border border-line-subtle bg-surface">
      <div v-for="field in props.fields" :key="field.label" class="flex items-start gap-4 px-3.5 py-3">
        <div class="w-52 shrink-0">
          <p class="text-xs font-medium text-fg-1">{{ field.label }}</p>
          <p class="mt-0.5 font-mono text-[0.625rem] leading-4 text-fg-3">{{ field.value }}</p>
        </div>
        <p class="min-w-0 flex-1 text-[0.6875rem] leading-4 text-fg-3" :class="VALUE_CLASS[field.tone]">
          {{ field.detail }}
        </p>
      </div>
    </div>

    <div v-if="props.resolved" class="grid gap-2 sm:grid-cols-2">
      <GovernPendingData
        title="Dead-letter item contents"
        contract="operator.platform.dlq.items.v1"
        description="Depth is a count. Which aggregates failed, why, and whether they can be replayed are not part of the health snapshot."
      />
      <GovernPendingData
        title="Outbox throughput and lag behind the watermark"
        contract="operator.platform.outbox.v1"
        description="The snapshot reports a position. Nothing here says how fast that position is moving or whether consumers are behind it."
      />
    </div>

    <GovernCaveat tone="info" :title="props.resolved ? 'These are readings, not rates' : 'Nothing is carried over'">
      {{
        props.resolved
          ? `Every value in this tab is one field of one ${PLATFORM_CONTRACT} snapshot. A lag of four seconds at observation time does not describe the last minute, and a depth of zero does not mean the queue was never non-empty.`
          : "The snapshot did not resolve, so each field is reported as unreported. The shape of this tab stays the same because an absent platform value is a fact the operator should be able to read."
      }}
    </GovernCaveat>
  </section>
</template>
