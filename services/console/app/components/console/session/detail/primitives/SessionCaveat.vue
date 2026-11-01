<script setup lang="ts">
import { Info } from "@lucide/vue"

withDefaults(
  defineProps<{
    summary: string
    detail?: string
    tone?: "muted" | "foreground"
  }>(),
  { detail: undefined, tone: "muted" },
)
</script>

<template>
  <details class="group/caveat min-w-0 text-xs leading-4">
    <summary
      class="flex cursor-pointer list-none items-start gap-1.5 rounded-sm text-fg-3 transition-colors hover:text-fg-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory [&::-webkit-details-marker]:hidden"
      :class="tone === 'foreground' && 'text-fg-2'"
    >
      <Info :size="12" :stroke-width="1.75" class="mt-0.5 shrink-0" aria-hidden="true" />
      <span class="min-w-0 flex-1">
        {{ summary }}
        <span v-if="detail" class="ml-1 inline-flex items-center gap-0.5 font-medium text-fg-2 underline decoration-line-strong underline-offset-2 group-open/caveat:hidden">
          Why?
        </span>
      </span>
    </summary>
    <p v-if="detail" class="mt-1 pl-[1.125rem] leading-4 text-fg-3 text-pretty">{{ detail }}</p>
  </details>
</template>
