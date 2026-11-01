<script setup lang="ts">
import { computed } from "vue"
import { ChevronRight } from "@lucide/vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import { formatGovernNumber } from "@/lib/govern-format"
import {
  policyRulesForSnapshot,
  policySnapshots,
  type PolicyRule,
  type PolicySnapshot,
} from "@/lib/policy-preview"
import { policySnapshotHref } from "@/lib/govern-query"

const props = defineProps<{
  rule: PolicyRule
  snapshot: PolicySnapshot
}>()

const publishedIn = computed(() =>
  policySnapshots
    .map((snapshot) => {
      const view = policyRulesForSnapshot(snapshot.id).find((entry) => entry.id === props.rule.id)
      return view ? { snapshot, revision: view.revision } : null
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null),
)

const matchingRuns = computed(() => props.rule.matches)
const totalMatches = computed(() => matchingRuns.value.reduce((sum, entry) => sum + entry.runs, 0))
</script>

<template>
  <div class="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
    <div class="flex min-w-0 flex-col gap-3">
      <section class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="rule-scope">
        <header class="border-b border-line-subtle px-4 py-2.5">
          <h2 id="rule-scope" class="text-sm font-semibold text-fg-1">Scope</h2>
          <p class="mt-0.5 text-xs text-fg-3">Where this rule is applied.</p>
        </header>
        <dl class="divide-y divide-line-subtle">
          <div class="flex items-baseline justify-between gap-3 px-4 py-2">
            <dt class="text-xs text-fg-3">Scope</dt>
            <dd class="font-mono text-[0.6875rem] text-fg-2">{{ rule.scope }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3 px-4 py-2">
            <dt class="text-xs text-fg-3">Area</dt>
            <dd class="text-xs text-fg-1">{{ rule.area }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3 px-4 py-2">
            <dt class="text-xs text-fg-3">Owner</dt>
            <dd class="text-xs text-fg-1">{{ rule.owner }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3 px-4 py-2">
            <dt class="text-xs text-fg-3">Rule ID</dt>
            <dd><GovernCopyId :id="rule.id" label="Rule ID" /></dd>
          </div>
        </dl>
      </section>

      <GovernPendingData
        title="Runtime precedence"
        contract="operator.policies.snapshots.v1"
        description="The snapshot contract does not expose rule ordering or scope precedence. This page cannot claim which rule wins when two rules match."
      />
    </div>

    <div class="flex min-w-0 flex-col gap-3">
      <section class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="rule-matches">
        <header class="flex items-baseline justify-between gap-2 border-b border-line-subtle px-4 py-2.5">
          <div>
            <h2 id="rule-matches" class="text-sm font-semibold text-fg-1">Agents this rule matched</h2>
            <p class="mt-0.5 text-xs text-fg-3">{{ matchingRuns.length }} agents · {{ formatGovernNumber(totalMatches) }} linked runs</p>
          </div>
        </header>
        <div v-if="matchingRuns.length === 0" class="px-4 py-6 text-xs text-fg-3">No agent has a linked run for this rule in the sample.</div>
        <ul v-else class="divide-y divide-line-subtle">
          <li v-for="match in matchingRuns" :key="match.agent" class="flex items-center justify-between gap-3 px-4 py-2">
            <span class="min-w-0 truncate text-xs text-fg-1">{{ match.agent }}</span>
            <span class="shrink-0 font-mono text-xs text-fg-2 tabular-nums">{{ formatGovernNumber(match.runs) }}</span>
          </li>
        </ul>
        <p class="border-t border-line-subtle px-4 py-2 text-[0.625rem] leading-3.5 text-fg-3">
          Counts come from linked decisions only; a run without a policy link is absent rather than unaffected.
        </p>
      </section>

      <section class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="rule-published">
        <header class="border-b border-line-subtle px-4 py-2.5">
          <h2 id="rule-published" class="text-sm font-semibold text-fg-1">Published in</h2>
          <p class="mt-0.5 text-xs text-fg-3">A revision behaves the same in every snapshot that carries it.</p>
        </header>
        <ul class="divide-y divide-line-subtle">
          <li v-for="entry in publishedIn" :key="entry.snapshot.id">
            <NuxtLink
              :to="policySnapshotHref(entry.snapshot.id)"
              class="flex items-center gap-2 px-4 py-2 transition-colors hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent-memory"
            >
              <span class="min-w-0 flex-1">
                <span class="block font-mono text-xs text-fg-1">{{ entry.snapshot.id }}</span>
                <span class="mt-0.5 block text-[0.625rem] text-fg-3">revision @{{ entry.revision.revision }} · {{ entry.snapshot.publishedBy }}</span>
              </span>
              <span v-if="entry.snapshot.id === snapshot.id" class="ix-preview-chip shrink-0">Shown</span>
              <ChevronRight :size="13" :stroke-width="1.9" class="shrink-0 text-fg-3" aria-hidden="true" />
            </NuxtLink>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
