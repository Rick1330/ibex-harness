<script setup lang="ts">
import { Check, CircleDashed, CircleDot } from "@lucide/vue"
import { formatGovernStamp } from "@/lib/govern-format"
import type { PolicyLifecycleStep } from "@/lib/policy-preview"

defineProps<{
  steps: PolicyLifecycleStep[]
}>()
</script>

<template>
  <ol class="grid gap-3 sm:grid-cols-5" aria-label="Snapshot lifecycle">
    <li v-for="(step, index) in steps" :key="step.id" class="relative min-w-0">
      <span
        v-if="index < steps.length - 1"
        class="absolute top-3 left-6 hidden h-px w-[calc(100%-1.5rem)] sm:block"
        :class="step.status === 'done' ? 'bg-ok/40' : 'bg-line-subtle'"
        aria-hidden="true"
      />
      <div class="relative flex items-start gap-2">
        <span
          class="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full border"
          :class="
            step.status === 'done'
              ? 'border-transparent bg-transparent text-ok'
              : step.status === 'pending'
                ? 'border-transparent bg-transparent text-warn'
                : 'border-dashed border-line-strong bg-surface-1 text-fg-3'
          "
          :title="step.detail"
        >
          <Check v-if="step.status === 'done'" :size="12" :stroke-width="2.4" aria-hidden="true" />
          <CircleDot v-else-if="step.status === 'pending'" :size="12" :stroke-width="2.2" aria-hidden="true" />
          <CircleDashed v-else :size="12" :stroke-width="2" aria-hidden="true" />
        </span>
        <div class="min-w-0">
          <p class="text-xs font-medium text-fg-1">{{ step.label }}</p>
          <p v-if="step.at" class="mt-0.5 text-[0.625rem] text-fg-2" :title="formatGovernStamp(step.at)">{{ formatGovernStamp(step.at).replace(' UTC', '') }}</p>
          <p v-else class="mt-0.5 text-[0.625rem] text-fg-3">Not recorded</p>
          <p v-if="step.status !== 'unknown'" class="mt-0.5 truncate text-[0.625rem] text-fg-3" :title="step.detail">
            {{ step.actor ?? step.detail }}
          </p>
        </div>
      </div>
    </li>
  </ol>
</template>
