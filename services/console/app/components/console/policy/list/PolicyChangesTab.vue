<script setup lang="ts">
import { computed } from "vue"
import { ArrowRight, ChevronRight } from "@lucide/vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernEffectTag from "@/components/console/govern/primitives/GovernEffectTag.vue"
import { formatGovernDate, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import { policyChangeFeed } from "@/lib/policy-preview"
import { policyRuleDetailHref, policySnapshotHref } from "@/lib/govern-query"

const changes = policyChangeFeed()

const groups = computed(() => {
  const map = new Map<string, typeof changes>()
  for (const change of changes) {
    const key = formatGovernDate(change.at)
    const list = map.get(key) ?? []
    list.push(change)
    map.set(key, list)
  }
  return [...map.entries()].map(([label, items]) => ({ label, items }))
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h2 class="text-sm font-semibold text-fg-1">Every published rule change</h2>
      <span class="font-mono text-[0.6875rem] text-fg-3">{{ changes.length }} revisions across {{ groups.length }} days</span>
    </div>

    <section v-for="group in groups" :key="group.label" class="min-w-0">
      <h3 class="sticky top-0 z-10 border-b border-line-subtle bg-canvas/95 px-1 py-1 text-[0.6875rem] font-semibold tracking-[0.08em] text-fg-3 uppercase backdrop-blur">
        {{ group.label }}
      </h3>
      <ol class="divide-y divide-line-subtle overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
        <li v-for="change in group.items" :key="change.id" class="flex min-w-0 flex-wrap items-start gap-x-4 gap-y-2 px-4 py-3">
          <div class="w-24 shrink-0">
            <span class="block text-xs text-fg-2" :title="formatGovernStamp(change.at)">{{ formatGovernRelative(change.at) }}</span>
            <span class="mt-0.5 block font-mono text-[0.625rem] text-fg-3">{{ change.snapshotId }}</span>
          </div>

          <div class="min-w-0 flex-1">
            <div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <NuxtLink
                :to="policyRuleDetailHref(change.ruleId, { tab: 'history', snapshot: change.snapshotId, rev: change.toRevision })"
                class="truncate text-[0.8125rem] font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline"
              >
                {{ change.label }}
              </NuxtLink>
              <GovernCopyId :id="change.ruleId" label="Rule ID" icon-only />
              <GovernEffectTag :effect="change.effect" />
              <span class="inline-flex items-center gap-1 font-mono text-[0.6875rem] text-fg-3">
                <template v-if="change.fromRevision">@{{ change.fromRevision }}</template>
                <span v-else>new</span>
                <ArrowRight :size="10" :stroke-width="2" aria-hidden="true" />
                @{{ change.toRevision }}
              </span>
            </div>
            <p class="mt-1 max-w-3xl text-xs leading-5 text-fg-2">{{ change.summary }}</p>
            <p class="mt-0.5 text-[0.6875rem] text-fg-3">Changed by {{ change.changedBy }}</p>
          </div>

          <NuxtLink
            :to="policySnapshotHref(change.snapshotId)"
            class="inline-flex size-7 shrink-0 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            :aria-label="`Open snapshot ${change.snapshotId}`"
          >
            <ChevronRight :size="15" :stroke-width="1.9" aria-hidden="true" />
          </NuxtLink>
        </li>
      </ol>
    </section>
  </div>
</template>
