<script setup lang="ts">
import { Hash } from "@lucide/vue"
import { shortDigest } from "@/lib/govern-format"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"

withDefaults(
  defineProps<{
    hash: string
    label?: string
  }>(),
  { label: "digest" },
)
</script>

<template>
  <span class="inline-flex min-w-0 items-center gap-1 rounded border border-line-subtle bg-surface-2 py-0.5 pr-0.5 pl-1.5">
    <Hash :size="10" :stroke-width="1.9" class="shrink-0 text-fg-3" aria-hidden="true" />
    <span class="truncate font-mono text-[0.6875rem] leading-4 text-fg-2 tabular-nums" :title="hash">
      {{ shortDigest(hash) }}
    </span>
    <GovernCopyId :id="hash" :label="label" icon-only />
  </span>
</template>
