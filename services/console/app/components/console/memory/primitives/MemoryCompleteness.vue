<script setup lang="ts">
import { computed } from "vue"
import type { MemoryDetail } from "@/lib/memory-detail-preview"
import { MEMORY_SOURCE_LABELS } from "@/lib/memory-preview"
import MemoryInfoHint from "./MemoryInfoHint.vue"

const props = defineProps<{ detail: MemoryDetail }>()

const fields = computed(() => [
  { name: "Subject", recorded: props.detail.subject !== null },
  { name: "Applies to", recorded: props.detail.appliesTo.length > 0 },
  { name: "Last verified", recorded: props.detail.lastVerifiedAt !== null },
  { name: "Expires", recorded: props.detail.memory.validUntil !== null },
  { name: "Confidence definition", recorded: props.detail.confidenceMeaning.definition !== null },
  { name: "Source turn", recorded: typeof props.detail.metadata.source_turn === "number" },
  { name: "Extractor", recorded: typeof props.detail.metadata.extractor === "string" },
  { name: "Created by user", recorded: props.detail.createdByUser !== null },
  { name: "Method", recorded: props.detail.memory.source === "user_provided" },
  { name: "Source excerpt", recorded: false },
  { name: "Evaluation timestamps", recorded: props.detail.evaluation.checks.every((check) => check.evaluatedAt !== null) },
  { name: "Per-event score components", recorded: false },
])

const recorded = computed(() => fields.value.filter((field) => field.recorded).length)
const total = computed(() => fields.value.length)
const missing = computed(() => fields.value.filter((field) => !field.recorded))
const sourceLabel = computed(() => MEMORY_SOURCE_LABELS[props.detail.memory.source])
</script>

<template>
  <section aria-labelledby="memory-completeness" class="rounded-lg border border-line-subtle bg-surface p-4">
    <div class="flex items-center justify-between gap-2">
      <h2 id="memory-completeness" class="text-sm leading-5 font-semibold text-fg-1">Data completeness</h2>
      <span class="font-mono text-xs text-fg-2 tabular-nums">{{ recorded }} of {{ total }} fields</span>
    </div>
    <div
      class="mt-2.5 flex h-1.5 overflow-hidden rounded-full bg-raised"
      role="img"
      :aria-label="`${recorded} of ${total} record fields are populated`"
    >
      <span
        class="h-full rounded-full bg-memory transition-[width] duration-300"
        :style="{ width: `${Math.round((recorded / total) * 100)}%` }"
      />
    </div>
    <p v-if="missing.length" class="mt-2.5 flex items-start gap-1.5 text-xs leading-4 text-fg-3">
      <span class="min-w-0 flex-1">
        Missing: {{ missing.map((field) => field.name.toLowerCase()).join(", ") }}.
      </span>
      <MemoryInfoHint label="Why fields are missing">
        <p class="font-medium text-fg-1">Why fields are missing</p>
        <p class="mt-1">
          Fields show as missing when this illustrative record never captured them. A live record returns the same shape;
          gaps are never backfilled with defaults. Source: {{ sourceLabel }}.
        </p>
      </MemoryInfoHint>
    </p>
    <p v-else class="mt-2.5 text-xs leading-4 text-fg-3">All tracked fields are recorded for this preview.</p>
  </section>
</template>
