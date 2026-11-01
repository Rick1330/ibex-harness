<script setup lang="ts">
withDefaults(defineProps<{ rows?: number; density?: "comfortable" | "compact" }>(), {
  rows: 9,
  density: "comfortable",
})
</script>

<template>
  <div aria-hidden="true" class="divide-y divide-line-subtle border-y border-line-subtle">
    <div
      v-for="index in rows"
      :key="index"
      class="flex items-center gap-3 px-2"
      :class="density === 'compact' ? 'h-9' : 'h-13'"
    >
      <span class="size-3.5 shrink-0 animate-pulse rounded bg-surface-2" />
      <div class="min-w-0 flex-1 space-y-1.5">
        <span class="block h-3 animate-pulse rounded bg-surface-2" :style="{ width: `${52 + ((index * 13) % 34)}%` }" />
        <span
          v-if="density !== 'compact'"
          class="block h-2 animate-pulse rounded bg-surface-2/70"
          :style="{ width: `${22 + ((index * 7) % 20)}%` }"
        />
      </div>
      <span class="hidden h-5 w-24 shrink-0 animate-pulse rounded-full bg-surface-2/70 sm:block" />
      <span class="hidden h-3 w-12 shrink-0 animate-pulse rounded bg-surface-2/70 md:block" />
      <span class="hidden h-3 w-24 shrink-0 animate-pulse rounded bg-surface-2/70 lg:block" />
      <span class="h-3 w-10 shrink-0 animate-pulse rounded bg-surface-2/70" />
    </div>
  </div>
  <p class="sr-only" role="status">Loading memories</p>
</template>
