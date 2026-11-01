<script setup lang="ts">
import { Inbox } from "@lucide/vue"

withDefaults(
  defineProps<{
    title: string
    reason?: string | null
    nextStep?: string | null
    actionLabel?: string | null
  }>(),
  { reason: null, nextStep: null, actionLabel: null },
)

const emit = defineEmits<{ action: [] }>()
</script>

<template>
  <div class="flex flex-col items-center gap-1.5 rounded-lg border border-dashed border-line-subtle bg-surface-1/40 px-4 py-10 text-center">
    <Inbox :size="20" :stroke-width="1.6" class="text-fg-3" aria-hidden="true" />
    <p class="text-sm font-medium text-fg-1">{{ title }}</p>
    <p v-if="reason" class="max-w-[52ch] text-xs leading-5 text-fg-3 text-pretty">{{ reason }}</p>
    <p v-if="nextStep" class="max-w-[52ch] text-xs leading-5 text-fg-2 text-pretty">{{ nextStep }}</p>
    <button
      v-if="actionLabel"
      type="button"
      class="ix-button-secondary mt-2 h-8 px-3 text-xs"
      @click="emit('action')"
    >
      {{ actionLabel }}
    </button>
  </div>
</template>
