<script setup lang="ts">
import { computed } from "vue"
import {
  CircleCheck,
  CircleDashed,
  CircleX,
  Eye,
  TriangleAlert,
} from "@lucide/vue"

export type VerdictTone =
  | "healthy"
  | "attention"
  | "down"
  | "unknown"
  | "preview"
  | "unavailable"

const props = withDefaults(
  defineProps<{
    tone: VerdictTone
    title: string
    body?: string
    eyebrow?: string
    meta?: string
  }>(),
  {
    body: undefined,
    eyebrow: undefined,
    meta: undefined,
  },
)

const icon = computed(() => {
  if (props.tone === "healthy") return CircleCheck
  if (props.tone === "attention") return TriangleAlert
  if (props.tone === "down") return CircleX
  if (props.tone === "preview") return Eye
  return CircleDashed
})
</script>

<template>
  <section
    class="ix-verdict"
    :data-tone="tone"
    :class="{ 'ix-preview-stripe': tone === 'preview' }"
    aria-live="polite"
  >
    <div class="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div class="flex min-w-0 items-start gap-3">
        <span class="ix-verdict-icon" aria-hidden="true">
          <component :is="icon" :size="20" :stroke-width="1.75" />
        </span>
        <div class="min-w-0">
          <p v-if="eyebrow" class="ix-label">{{ eyebrow }}</p>
          <h2 class="ix-heading mt-0.5 text-fg-1">{{ title }}</h2>
          <p v-if="body" class="mt-1 max-w-3xl text-sm leading-5 text-fg-2">{{ body }}</p>
        </div>
      </div>
      <div v-if="meta || $slots.meta || $slots.actions" class="flex shrink-0 flex-col gap-2 sm:items-end">
        <span v-if="meta" class="font-mono text-[0.8125rem] text-fg-3">{{ meta }}</span>
        <slot name="meta" />
        <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2 sm:justify-end">
          <slot name="actions" />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.ix-verdict {
  --verdict-tone: var(--ix-fg-3);
  border: 1px solid color-mix(in srgb, var(--verdict-tone) 24%, var(--ix-line-subtle));
  border-left: 3px solid var(--verdict-tone);
  border-radius: 10px;
  background: color-mix(in srgb, var(--verdict-tone) 3%, var(--ix-surface));
  padding: 1.125rem 1.25rem;
}

.ix-verdict[data-tone="healthy"] {
  --verdict-tone: var(--ix-ok);
}

.ix-verdict[data-tone="attention"] {
  --verdict-tone: var(--ix-warn);
}

.ix-verdict[data-tone="down"],
.ix-verdict[data-tone="unavailable"] {
  --verdict-tone: var(--ix-crit);
}

.ix-verdict[data-tone="preview"] {
  --verdict-tone: var(--ix-line-strong);
  background: var(--ix-surface);
  padding-top: 1rem;
}

.ix-verdict-icon {
  display: inline-flex;
  width: 2.5rem;
  height: 2.5rem;
  flex: none;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--verdict-tone) 36%, var(--ix-line-subtle));
  border-radius: 6px;
  background: color-mix(in srgb, var(--verdict-tone) 8%, var(--ix-surface));
  color: var(--verdict-tone);
}
</style>
