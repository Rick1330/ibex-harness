<script setup lang="ts">
import { computed } from "vue"
import { ArrowRight, Check } from "@lucide/vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernDiffSummaryBar from "@/components/console/govern/primitives/GovernDiffSummaryBar.vue"
import GovernEffectTag from "@/components/console/govern/primitives/GovernEffectTag.vue"
import GovernModeTag from "@/components/console/govern/primitives/GovernModeTag.vue"
import GovernSectionDiff from "@/components/console/govern/primitives/GovernSectionDiff.vue"
import { diffSummary } from "@/lib/govern-diff"
import { formatGovernShortDate, formatGovernStamp } from "@/lib/govern-format"
import {
  policyRevisionSections,
  type PolicyRule,
  type PolicyRuleRevision,
} from "@/lib/policy-preview"

const props = defineProps<{
  rule: PolicyRule
  revision: PolicyRuleRevision
}>()

const emit = defineEmits<{ revision: [revision: number] }>()

const selected = computed(() => props.revision.revision)
const previous = computed(() => props.rule.revisions.find((entry) => entry.revision === selected.value - 1) ?? null)
const sections = computed(() => policyRevisionSections(props.rule, selected.value))
const summary = computed(() => diffSummary(sections.value))

function select(revision: number): void {
  emit("revision", revision)
}
</script>

<template>
  <div class="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,17rem)_minmax(0,1fr)]">
    <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="rule-history-list">
      <header class="border-b border-line-subtle px-4 py-2.5">
        <h2 id="rule-history-list" class="text-sm font-semibold text-fg-1">Revisions</h2>
        <p class="mt-0.5 text-xs text-fg-3">{{ rule.revisions.length }} recorded · newest first</p>
      </header>
      <ol class="divide-y divide-line-subtle">
        <li v-for="entry in rule.revisions" :key="entry.revision">
          <button
            type="button"
            class="flex w-full items-start gap-2 px-4 py-2.5 text-left transition-colors hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent-memory"
            :class="entry.revision === selected && 'bg-surface-2'"
            :aria-current="entry.revision === selected ? 'true' : undefined"
            @click="select(entry.revision)"
          >
            <span class="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full border" :class="entry.revision === selected ? 'border-accent/40 bg-accent-tint text-accent' : 'border-line-subtle bg-surface-1 text-fg-3'">
              <Check v-if="entry.revision === selected" :size="11" :stroke-width="2.4" aria-hidden="true" />
              <span v-else class="font-mono text-[0.5625rem]">{{ entry.revision }}</span>
            </span>
            <span class="min-w-0 flex-1">
              <span class="flex flex-wrap items-center gap-1.5">
                <span class="font-mono text-xs text-fg-1">@{{ entry.revision }}</span>
                <GovernEffectTag :effect="entry.effect" />
              </span>
              <span class="mt-1 block text-[0.625rem] text-fg-3" :title="formatGovernStamp(entry.effectiveFrom)">
                {{ formatGovernShortDate(entry.effectiveFrom) }} · {{ entry.changedBy }}
              </span>
              <span class="mt-0.5 block truncate text-[0.6875rem] text-fg-2">{{ entry.changeSummary }}</span>
            </span>
          </button>
        </li>
      </ol>
    </section>

    <section class="min-w-0 rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="rule-history-diff">
      <header class="flex flex-wrap items-center justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
        <div class="min-w-0">
          <h2 id="rule-history-diff" class="text-sm font-semibold text-fg-1">
            {{ previous ? `What changed from @${previous.revision} to @${selected}` : `First published revision @${selected}` }}
          </h2>
          <p class="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-fg-3">
            <GovernEffectTag :effect="revision.effect" />
            <GovernModeTag :mode="revision.mode" />
            <span :title="formatGovernStamp(revision.effectiveFrom)">{{ formatGovernShortDate(revision.effectiveFrom) }}</span>
            <span aria-hidden="true">·</span>
            <span>{{ revision.changedBy }}</span>
          </p>
        </div>
        <GovernDiffSummaryBar :summary="summary" :from="previous ? `@${previous.revision}` : null" :to="`@${selected}`" />
      </header>
      <div class="p-3">
        <GovernCaveat v-if="!previous" tone="info">
          This is the first published revision, so every line is new. There is no earlier revision to compare.
        </GovernCaveat>
        <div :class="!previous && 'mt-3'">
          <GovernSectionDiff :sections="sections" mode="unified" :from-label="`@${previous?.revision ?? '—'}`" :to-label="`@${selected}`" />
        </div>
      </div>
      <footer class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line-subtle bg-canvas/30 px-4 py-2 text-[0.6875rem] leading-4 text-fg-3">
        <span>Revision hashes are recorded per revision; a rule cannot change inside a published snapshot.</span>
        <button
          v-if="previous"
          type="button"
          class="ml-auto inline-flex items-center gap-1 text-fg-2 hover:text-fg-1"
          @click="select(previous.revision)"
        >
          View previous <ArrowRight :size="11" :stroke-width="2" aria-hidden="true" />
        </button>
      </footer>
    </section>
  </div>
</template>
