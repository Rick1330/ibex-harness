<script setup lang="ts">
import { computed } from "vue"
import { Cog, Cpu, KeyRound, Plug, ShieldCheck, UserRound } from "@lucide/vue"
import { AUDIT_ACTOR_TYPE_LABELS, type AuditActorType } from "@/lib/audit-preview"

const props = withDefaults(
  defineProps<{
    name: string
    type: AuditActorType
    stepUp?: boolean
    /** Second line under the name, e.g. "Person · step-up". */
    subline?: string | null
    size?: "sm" | "md"
  }>(),
  { stepUp: false, subline: null, size: "md" },
)

const icon = computed(() => {
  switch (props.type) {
    case "person":
      return UserRound
    case "service":
      return Cog
    case "policy":
      return ShieldCheck
    case "system":
      return Cpu
    case "relay":
      return Plug
    default:
      return KeyRound
  }
})

const initials = computed(() =>
  props.name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join(""),
)

const line = computed(() => {
  if (props.subline) return props.subline
  const base = AUDIT_ACTOR_TYPE_LABELS[props.type]
  return props.stepUp ? `${base} · step-up` : base
})

const avatarClass = computed(() =>
  props.type === "person"
    ? "border-accent/25 bg-accent-tint text-accent"
    : "border-line-subtle bg-raised text-fg-2",
)
</script>

<template>
  <span class="flex min-w-0 items-center gap-2">
    <span
      class="inline-flex shrink-0 items-center justify-center rounded-full border font-semibold"
      :class="[avatarClass, size === 'sm' ? 'size-6 text-[0.625rem]' : 'size-7 text-[0.6875rem]']"
      :title="name"
      aria-hidden="true"
    >
      <template v-if="type === 'person'">{{ initials }}</template>
      <component :is="icon" v-else :size="size === 'sm' ? 12 : 14" :stroke-width="1.9" />
    </span>
    <span class="min-w-0">
      <span class="block truncate text-[0.8125rem] leading-4 font-medium text-fg-1">{{ name }}</span>
      <span class="block truncate text-[0.6875rem] leading-4 text-fg-3">{{ line }}</span>
    </span>
  </span>
</template>
