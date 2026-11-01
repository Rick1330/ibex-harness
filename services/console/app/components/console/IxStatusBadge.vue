<script setup lang="ts">
import { computed } from "vue"
import {
  CircleCheck,
  CircleDashed,
  CircleX,
  Clock,
  Eye,
  Radio,
  TriangleAlert,
} from "@lucide/vue"

export type IxStatus =
  | "healthy"
  | "degraded"
  | "down"
  | "unknown"
  | "live"
  | "stale"
  | "preview"

const props = withDefaults(
  defineProps<{
    status: IxStatus
    label?: string
    detail?: string
    size?: "sm" | "md"
  }>(),
  {
    label: undefined,
    detail: undefined,
    size: "sm",
  },
)

const defaultLabel: Record<IxStatus, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
  unknown: "Unknown",
  live: "Live",
  stale: "Stale",
  preview: "Preview",
}

const icon = computed(() => {
  if (props.status === "healthy") return CircleCheck
  if (props.status === "degraded") return TriangleAlert
  if (props.status === "down") return CircleX
  if (props.status === "unknown") return CircleDashed
  if (props.status === "live") return Radio
  if (props.status === "stale") return Clock
  return Eye
})

const text = computed(() => props.label ?? defaultLabel[props.status])
const tone = computed(() => {
  if (props.status === "healthy" || props.status === "live") return "ok"
  if (props.status === "degraded" || props.status === "stale") return "warn"
  if (props.status === "down") return "crit"
  if (props.status === "preview") return "preview"
  return "muted"
})
const aria = computed(() =>
  props.detail ? `${text.value}. ${props.detail}` : `${text.value}.`,
)
</script>

<template>
  <span class="ix-status" :data-tone="tone" :data-size="size" :aria-label="aria">
    <span v-if="status === 'live'" class="ix-live-dot" aria-hidden="true" />
    <component :is="icon" v-else class="ix-status-icon" :size="size === 'sm' ? 12 : 14" :stroke-width="1.75" aria-hidden="true" />
    <span>{{ text }}</span>
    <span v-if="detail" class="ix-status-detail">{{ detail }}</span>
  </span>
</template>

<style scoped>
.ix-status {
  display: inline-flex;
  min-height: 1.75rem;
  align-items: center;
  gap: 0.375rem;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 9999px;
  padding: 0 0.5rem;
  font-size: 0.8125rem;
  font-weight: 500;
  line-height: 1;
  color: var(--ix-fg-2);
  white-space: nowrap;
}

.ix-status[data-size="sm"] {
  min-height: 1.625rem;
  padding: 0 0.5625rem;
  font-size: 0.8125rem;
}

.ix-status[data-tone="ok"] {
  border-color: color-mix(in srgb, var(--ix-ok) 42%, var(--ix-line-subtle));
  color: var(--ix-ok);
}

.ix-status[data-tone="warn"] {
  border-color: color-mix(in srgb, var(--ix-warn) 48%, var(--ix-line-subtle));
  color: var(--ix-warn);
}

.ix-status[data-tone="crit"] {
  border-color: color-mix(in srgb, var(--ix-crit) 44%, var(--ix-line-subtle));
  color: var(--ix-crit);
}

.ix-status[data-tone="preview"] {
  border-style: dashed;
  color: var(--ix-fg-2);
}

.ix-status[data-tone="muted"] {
  color: var(--ix-fg-3);
}

.ix-status-icon {
  flex: none;
}

.ix-live-dot {
  width: 0.375rem;
  height: 0.375rem;
  flex: none;
  border-radius: 9999px;
  background: var(--ix-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ix-accent) 16%, transparent);
}

.ix-status-detail {
  margin-left: 0.125rem;
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  font-weight: 400;
  color: var(--ix-fg-3);
}
</style>
