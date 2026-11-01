<script setup lang="ts">
import { computed } from "vue"
import { ChevronDown, GitCompareArrows, Info, Radio } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernHashTag from "@/components/console/govern/primitives/GovernHashTag.vue"
import { formatGovernShortDate, formatGovernStamp } from "@/lib/govern-format"
import {
  policySnapshotChangeSummary,
  policySnapshotState,
  type PolicySnapshot,
} from "@/lib/policy-preview"
import { policyCompareHref, policySnapshotHref } from "@/lib/govern-query"

const props = defineProps<{
  snapshot: PolicySnapshot
  snapshots: PolicySnapshot[]
}>()

const emit = defineEmits<{ "update:snapshot": [id: string] }>()

const state = computed(() => policySnapshotState(props.snapshot.id))
const changes = computed(() => policySnapshotChangeSummary(props.snapshot.id))
const compareHref = computed(() =>
  props.snapshot.previousId
    ? policyCompareHref({ from: props.snapshot.previousId, to: props.snapshot.id, hideUnchanged: false })
    : policyCompareHref({ from: props.snapshot.id, to: props.snapshot.id, hideUnchanged: false }),
)

const changeText = computed(() => {
  if (changes.value.metadataOnly) return "Metadata only"
  if (changes.value.changed === 0) return "No rule changes"
  return `${changes.value.changed} ${changes.value.changed === 1 ? "rule changed" : "rules changed"}`
})
</script>

<template>
  <section
    class="flex min-h-14 flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-line-subtle bg-surface-1 px-3 py-2"
    aria-label="Snapshot in force"
  >
    <span
      class="inline-flex h-5.5 shrink-0 items-center gap-1.5 rounded-full border px-2 text-xs leading-none font-medium"
      :class="state === 'live' ? 'border-transparent bg-transparent text-ok' : 'border-line bg-raised text-fg-2'"
    >
      <Radio :size="11" :stroke-width="2.2" aria-hidden="true" />
      {{ state === "live" ? "Current" : "Superseded" }}
    </span>

    <div class="flex min-w-0 items-center gap-2">
      <NuxtLink
        :to="policySnapshotHref(snapshot.id)"
        class="shrink-0 font-mono text-sm font-semibold text-fg-1 underline decoration-line-strong underline-offset-3 hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
      >
        {{ snapshot.id }}
      </NuxtLink>
      <GovernCopyId :id="snapshot.id" label="Snapshot ID" icon-only />
      <GovernHashTag :hash="snapshot.digest" label="snapshot digest" />
    </div>

    <dl class="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 text-[0.6875rem] leading-4">
      <div class="flex items-baseline gap-1">
        <dt class="text-fg-3">Effective</dt>
        <dd class="text-fg-2">
          <span :title="formatGovernStamp(snapshot.effectiveFrom)">{{ formatGovernShortDate(snapshot.effectiveFrom) }}</span>
        </dd>
      </div>
      <div class="flex items-baseline gap-1">
        <dt class="text-fg-3">Published by</dt>
        <dd class="text-fg-2">{{ snapshot.publishedBy }}</dd>
      </div>
      <div class="flex items-baseline gap-1">
        <dt class="text-fg-3">Change</dt>
        <dd class="flex items-center gap-1 text-fg-2">
          {{ changeText }}
          <Tooltip v-if="changes.metadataOnly" :delay-duration="120">
            <TooltipTrigger as-child>
              <span tabindex="0" class="inline-flex text-fg-3"><Info :size="11" :stroke-width="1.9" aria-hidden="true" /></span>
            </TooltipTrigger>
            <TooltipContent side="top" class="!max-w-72 !text-xs">{{ changes.reason }}</TooltipContent>
          </Tooltip>
        </dd>
      </div>
    </dl>

    <div class="ml-auto flex shrink-0 items-center gap-2">
      <label class="relative inline-flex h-8 items-center gap-1.5 rounded-md border border-line-subtle bg-surface px-2 text-xs text-fg-3">
        <span class="sr-only">Snapshot</span>
        <select
          :value="snapshot.id"
          aria-label="Switch snapshot"
          class="cursor-pointer appearance-none bg-transparent pr-4 font-mono text-[0.6875rem] font-medium text-fg-1 outline-none"
          @change="emit('update:snapshot', ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="entry in snapshots" :key="entry.id" :value="entry.id">
            {{ entry.id }} · {{ formatGovernShortDate(entry.effectiveFrom) }}
          </option>
        </select>
        <ChevronDown :size="11" :stroke-width="2" class="pointer-events-none absolute right-2 text-fg-3" aria-hidden="true" />
      </label>
      <NuxtLink
        :to="compareHref"
        class="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-fg-2 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
      >
        <GitCompareArrows :size="12" :stroke-width="1.9" aria-hidden="true" />
        Compare
      </NuxtLink>
    </div>
  </section>
</template>
