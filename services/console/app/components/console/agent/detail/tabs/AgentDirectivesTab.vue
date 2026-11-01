<script setup lang="ts">
import { computed, ref } from "vue"
import { GitCompare, Lock } from "@lucide/vue"
import AgentVersionTag from "../../primitives/AgentVersionTag.vue"
import AgentCopyId from "../../primitives/AgentCopyId.vue"
import AgentLockedAction from "../../primitives/AgentLockedAction.vue"
import { useAgentTabQueryBoolean } from "@/composables/useAgentTabQuery"
import { diffWords } from "@/lib/text-diff"
import { formatAgentCount, formatAgentDate, formatAgentStamp } from "@/lib/agent-detail"
import type { AgentDetail } from "@/lib/agent-preview"

const props = defineProps<{ agent: AgentDetail }>()

const directive = computed(() => props.agent.directive)
const hasPreviousDirectiveVersion = computed(() => {
  const current = directive.value
  return current !== null && current.versions.some((version) => version.version < current.version)
})
const showAll = useAgentTabQueryBoolean("dall")
const compareMode = useAgentTabQueryBoolean("dcompare")
const compareLeft = ref<number | null>(null)
const compareRight = ref<number | null>(null)

const VISIBLE_LINES = 24

const visibleBody = computed(() => {
  if (!directive.value) return []
  return showAll.value || directive.value.body.length <= VISIBLE_LINES
    ? directive.value.body
    : directive.value.body.slice(0, VISIBLE_LINES)
})

const compare = computed(() => {
  if (!directive.value || compareLeft.value === null || compareRight.value === null) return null
  const left = directive.value.versions.find((version) => version.version === compareLeft.value)
  const right = directive.value.versions.find((version) => version.version === compareRight.value)
  if (!left || !right) return null
  return {
    left,
    right,
    tokens: diffWords(left.body.join(" "), right.body.join(" ")),
  }
})

function toggleCompare(version: number): void {
  compareMode.value = true
  if (compareLeft.value === null) {
    compareLeft.value = version
  } else if (compareRight.value === null && version !== compareLeft.value) {
    compareRight.value = version
  } else {
    compareLeft.value = version
    compareRight.value = null
  }
}
</script>

<template>
  <div class="min-w-0">
    <template v-if="directive">
      <div class="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(16rem,1fr)]">
        <section aria-labelledby="directive-active" class="rounded-lg border border-line-subtle bg-surface-1 p-5">
          <div class="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="directive-active" class="text-sm leading-5 font-semibold text-fg-1">{{ directive.name }}</h2>
            <AgentVersionTag label="Directive" :value="`v${directive.version}`" tone="default" />
          </div>
          <p class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs leading-4 text-fg-3">
            <AgentCopyId :id="directive.hash" label="Directive hash" truncate />
            <span aria-hidden="true">·</span>
            <span>Effective since {{ formatAgentDate(directive.effectiveSince) }}</span>
            <span aria-hidden="true">·</span>
            <span :title="formatAgentStamp(directive.effectiveSince)">by {{ directive.author }}</span>
            <span aria-hidden="true">·</span>
            <span>{{ directive.resolvedFrom }}</span>
          </p>

          <div class="mt-4 border-l-2 border-line-strong pl-4">
            <p class="text-[0.6875rem] leading-4 font-medium tracking-[0.06em] text-fg-3 uppercase">Instruction text</p>
            <ol class="mt-2 max-w-[72ch] font-mono text-xs leading-6">
              <li
                v-for="(line, index) in visibleBody"
                :key="index"
                class="flex gap-3"
                :class="directive.sensitiveLines.includes(index) && 'italic text-fg-off'"
              >
                <span class="w-6 shrink-0 text-right text-fg-off tabular-nums select-none">{{ index + 1 }}</span>
                <span class="min-w-0 break-words text-fg-2">{{ directive.sensitiveLines.includes(index) ? "[redacted · privileged reveal required]" : line }}</span>
              </li>
            </ol>
            <button
              v-if="directive.body.length > VISIBLE_LINES && !showAll"
              type="button"
              class="mt-2 text-xs font-medium text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1"
              @click="showAll = true"
            >
              Show all ({{ directive.body.length }} lines)
            </button>
          </div>

          <div class="mt-4 flex flex-wrap items-center gap-2.5 border-t border-line-subtle pt-4">
            <AgentLockedAction label="Deactivate" size="sm" />
            <AgentLockedAction
              v-if="hasPreviousDirectiveVersion"
              :label="`Roll back to v${directive.version - 1}`"
              size="sm"
            />
            <p class="flex items-center gap-1.5 text-xs leading-4 text-fg-3">
              <Lock :size="11" :stroke-width="1.9" aria-hidden="true" />
              Live sessions keep v{{ directive.version }} until they end.
            </p>
          </div>
        </section>

        <aside class="min-w-0 space-y-4 xl:sticky xl:top-[6.5rem]" aria-label="Directive versions">
          <section class="rounded-lg border border-line-subtle bg-surface-1 p-4" aria-labelledby="directive-versions">
            <h2 id="directive-versions" class="flex items-center gap-1.5 text-sm leading-5 font-semibold text-fg-1">
              Version history
              <span v-if="compareMode" class="font-mono text-[0.625rem] font-normal text-fg-3">select two to compare</span>
            </h2>
            <ol class="mt-3 border-l border-line-subtle pl-4">
              <li v-for="version in directive.versions" :key="version.version" class="relative pb-4 last:pb-0">
                <span
                  class="absolute top-1.5 -left-[1.1875rem] size-2 rounded-full border"
                  :class="version.current ? 'border-memory bg-memory' : 'border-line-strong bg-surface-1'"
                  aria-hidden="true"
                />
                <button
                  type="button"
                  class="flex w-full flex-wrap items-baseline gap-x-2 gap-y-0.5 text-left text-xs"
                  :class="(compareLeft === version.version || compareRight === version.version) ? 'text-accent-memory' : 'text-fg-2 hover:text-fg-1'"
                  @click="toggleCompare(version.version)"
                >
                  <span class="font-mono font-medium">v{{ version.version }}</span>
                  <span class="font-mono text-[0.625rem] text-fg-3" :title="formatAgentStamp(version.effectiveSince)">{{ formatAgentDate(version.effectiveSince) }}</span>
                  <span class="text-fg-3">· {{ version.author }}</span>
                  <span v-if="version.current" class="rounded-full border border-memory/40 bg-memory-tint px-1.5 py-px text-[0.625rem] text-accent-memory">Active</span>
                </button>
                <p class="mt-0.5 text-xs leading-4 text-fg-3">{{ version.summary }}</p>
                <p class="mt-0.5 font-mono text-[0.625rem] text-fg-3">used in {{ formatAgentCount(version.usedInRuns) }} runs</p>
                <p v-if="version.version === directive.version && agent.drift === 'drifted'" class="mt-0.5 text-xs leading-4 text-warn">
                  ⚠ Error fingerprint changed after this version
                </p>
              </li>
            </ol>
          </section>

          <section
            v-if="compare"
            class="rounded-lg border border-line-subtle bg-surface-1 p-4"
            aria-labelledby="directive-compare"
          >
            <h2 id="directive-compare" class="flex items-center gap-1.5 text-sm leading-5 font-semibold text-fg-1">
              <GitCompare :size="13" :stroke-width="1.9" aria-hidden="true" />
              v{{ compare.left.version }} → v{{ compare.right.version }}
            </h2>
            <p class="mt-2 max-h-64 overflow-auto pr-1 text-xs leading-5 text-fg-2 text-pretty ix-scroll">
              <template v-for="(token, index) in compare.tokens" :key="index">
                <del v-if="token.type === 'removed'" class="rounded-sm bg-crit-tint px-0.5 text-fg-3 line-through decoration-crit/60">−{{ token.text }}</del>
                <ins v-else-if="token.type === 'added'" class="rounded-sm bg-ok-tint px-0.5 text-fg-1 no-underline">+{{ token.text }}</ins>
                <template v-else>{{ token.text }}</template>
              </template>
            </p>
          </section>
        </aside>
      </div>
    </template>

    <div v-else class="rounded-lg border border-dashed border-line px-5 py-8 text-center">
      <p class="text-sm font-medium text-fg-1">No directive is set</p>
      <p class="mt-1 text-xs leading-4 text-fg-3">The agent runs on its base model behaviour.</p>
    </div>
  </div>
</template>
