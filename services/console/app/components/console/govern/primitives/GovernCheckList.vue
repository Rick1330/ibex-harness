<script setup lang="ts">
import { Check, CircleDashed, CircleMinus, CircleSlash, Clock, X } from "@lucide/vue"
import { formatGovernStamp } from "@/lib/govern-format"

type GovernCheckItem = {
  id: string
  name: string
  state: "passed" | "pending" | "failed" | "skipped" | "not_configured"
  result: string | null
  actor?: string | null
  at?: string | null
  evidence?: { label: string; href: string } | null
}

withDefaults(
  defineProps<{
    items: GovernCheckItem[]
    emptyLabel?: string
  }>(),
  { emptyLabel: "No checks recorded for this version." },
)

const config = {
  passed: { icon: Check, label: "Passed", tone: "border-transparent bg-transparent text-ok" },
  pending: { icon: Clock, label: "Pending", tone: "border-transparent bg-transparent text-warn" },
  failed: { icon: X, label: "Failed", tone: "border-transparent bg-transparent text-crit" },
  skipped: { icon: CircleMinus, label: "Skipped", tone: "border-line bg-raised text-fg-3" },
  not_configured: { icon: CircleSlash, label: "Not configured", tone: "border-dashed border-line bg-transparent text-fg-3" },
} as const
</script>

<template>
  <ul v-if="items.length" class="divide-y divide-line-subtle overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
    <li v-for="item in items" :key="item.id" class="flex items-start gap-3 px-3 py-2.5">
      <span
        class="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full border"
        :class="config[item.state].tone"
        :title="config[item.state].label"
      >
        <component :is="config[item.state].icon" :size="11" :stroke-width="2.2" aria-hidden="true" />
      </span>
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <p class="text-xs font-medium text-fg-1">{{ item.name }}</p>
          <span class="text-[0.6875rem] text-fg-3">{{ config[item.state].label }}</span>
        </div>
        <p v-if="item.result" class="mt-0.5 text-xs leading-5 text-fg-2">{{ item.result }}</p>
        <p v-if="item.actor || item.at" class="mt-0.5 flex flex-wrap items-center gap-x-2 font-mono text-[0.625rem] text-fg-3">
          <span v-if="item.actor">{{ item.actor }}</span>
          <span v-if="item.at">{{ formatGovernStamp(item.at) }}</span>
        </p>
      </div>
      <NuxtLink
        v-if="item.evidence"
        :to="item.evidence.href"
        class="ix-link mt-0.5 shrink-0 font-mono text-[0.625rem]"
      >{{ item.evidence.label }}</NuxtLink>
    </li>
  </ul>
  <div v-else class="flex items-center gap-2 rounded-lg border border-dashed border-line-subtle bg-surface-1/40 px-3 py-4 text-xs text-fg-3">
    <CircleDashed :size="14" :stroke-width="1.8" aria-hidden="true" />
    {{ emptyLabel }}
  </div>
</template>
