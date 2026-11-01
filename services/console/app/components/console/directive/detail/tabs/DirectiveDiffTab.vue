<script setup lang="ts">
import { computed } from "vue"
import { ArrowLeftRight, TriangleAlert } from "@lucide/vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernDiffSummaryBar from "@/components/console/govern/primitives/GovernDiffSummaryBar.vue"
import GovernSectionDiff from "@/components/console/govern/primitives/GovernSectionDiff.vue"
import GovernVersionTag from "@/components/console/govern/primitives/GovernVersionTag.vue"
import {
  directiveDiff,
  directiveVersion,
  type Directive,
  type DirectiveVersion,
} from "@/lib/directive-preview"
import {
  DIRECTIVE_DIFF_MODES,
  DIRECTIVE_DIFF_MODE_LABELS,
  type DirectiveDetailDefaults,
  type DirectiveDetailState,
  type DirectiveDiffMode,
} from "@/lib/govern-query"

const props = defineProps<{
  directive: Directive
  state: DirectiveDetailState
  defaults: DirectiveDetailDefaults
}>()

const emit = defineEmits<{ update: [state: DirectiveDetailState] }>()

function update(patch: Partial<DirectiveDetailState>): void {
  emit("update", { ...props.state, ...patch })
}

const fromVersion = computed(() => directiveVersion(props.directive, props.state.from))
const toVersion = computed(() => directiveVersion(props.directive, props.state.to))
const diff = computed(() => directiveDiff(props.directive, props.state.from, props.state.to))
const identical = computed(() => props.state.from === props.state.to)
const changedSections = computed(() => diff.value.sections.filter((section) => section.changed))
const riskFlags = computed(() => toVersion.value?.riskFlags ?? [])

function swap(): void {
  update({ from: props.state.to, to: props.state.from })
}

function reset(): void {
  update({ from: props.defaults.from, to: props.defaults.to })
}

function describedState(version: DirectiveVersion | null): string {
  return version ? `${version.version} · ${version.state}` : "missing version"
}
</script>

<template>
  <div class="min-w-0 space-y-4">
    <div class="rounded-lg border border-line-subtle bg-surface-1 p-3">
      <div class="flex flex-wrap items-end gap-2">
        <label class="flex min-w-0 flex-col gap-1">
          <span class="text-[0.6875rem] leading-4 text-fg-3">From</span>
          <select
            :value="state.from"
            class="ix-input h-8 min-w-[9rem] text-xs"
            aria-label="Compare from version"
            @change="update({ from: ($event.target as HTMLSelectElement).value })"
          >
            <option v-for="version in directive.versions" :key="version.version" :value="version.version">
              {{ describedState(version) }}
            </option>
          </select>
        </label>

        <button
          type="button"
          class="mb-0.5 inline-flex size-8 items-center justify-center rounded-md border border-line-subtle bg-surface-1 text-fg-3 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          aria-label="Swap compared versions"
          @click="swap"
        >
          <ArrowLeftRight :size="13" :stroke-width="1.9" aria-hidden="true" />
        </button>

        <label class="flex min-w-0 flex-col gap-1">
          <span class="text-[0.6875rem] leading-4 text-fg-3">To</span>
          <select
            :value="state.to"
            class="ix-input h-8 min-w-[9rem] text-xs"
            aria-label="Compare to version"
            @change="update({ to: ($event.target as HTMLSelectElement).value })"
          >
            <option v-for="version in directive.versions" :key="version.version" :value="version.version">
              {{ describedState(version) }}
            </option>
          </select>
        </label>

        <div class="mb-0.5 ml-auto flex items-center gap-2">
          <button
            v-if="state.from !== defaults.from || state.to !== defaults.to"
            type="button"
            class="h-8 rounded-md px-2 text-xs text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            @click="reset"
          >
            Reset
          </button>
          <div class="flex rounded-md border border-line-subtle bg-surface-1 p-0.5" role="group" aria-label="Diff view mode">
            <button
              v-for="mode in DIRECTIVE_DIFF_MODES"
              :key="mode"
              type="button"
              class="h-7 rounded px-2 text-[0.6875rem] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
              :class="state.mode === mode ? 'bg-raised text-fg-1 shadow-sm' : 'text-fg-3 hover:text-fg-1'"
              :aria-pressed="state.mode === mode"
              @click="update({ mode: mode as DirectiveDiffMode })"
            >
              {{ DIRECTIVE_DIFF_MODE_LABELS[mode] }}
            </button>
          </div>
        </div>
      </div>

      <div class="mt-3 flex flex-wrap items-center gap-2 border-t border-line-subtle pt-3">
        <GovernDiffSummaryBar :summary="diff.summary" :from="fromVersion?.version ?? state.from" :to="toVersion?.version ?? state.to" />
        <span v-if="changedSections.length" class="text-[0.6875rem] leading-4 text-fg-3">
          {{ changedSections.map((section) => section.label).join(" · ") }}
        </span>
      </div>
    </div>

    <GovernCaveat v-if="identical" tone="info" title="Same version on both sides">
      Choose two different versions to see a text diff.
    </GovernCaveat>

    <GovernCaveat v-else-if="toVersion?.summary" tone="info" :title="`Change note for ${toVersion.version}`">
      {{ toVersion.summary }}
    </GovernCaveat>

    <section v-if="riskFlags.length" class="rounded-lg border border-warn/30 bg-warn-tint/30 p-3" aria-labelledby="diff-risk-title">
      <h2 id="diff-risk-title" class="flex items-center gap-1.5 text-xs font-semibold text-warn">
        <TriangleAlert :size="13" :stroke-width="1.9" aria-hidden="true" />
        Risk flags recorded on {{ toVersion?.version }}
      </h2>
      <ul class="mt-1.5 flex flex-wrap gap-1.5">
        <li v-for="flag in riskFlags" :key="flag" class="rounded-full border border-warn/30 bg-warn-tint px-2 py-0.5 text-[0.6875rem] leading-4 text-warn">
          {{ flag }}
        </li>
      </ul>
    </section>

    <div class="flex flex-wrap items-center gap-2">
      <GovernVersionTag label="From" :value="fromVersion?.version ?? state.from" tone="default" />
      <span class="text-fg-3" aria-hidden="true">→</span>
      <GovernVersionTag label="To" :value="toVersion?.version ?? state.to" tone="default" />
    </div>

    <GovernSectionDiff
      :sections="diff.sections"
      :mode="state.mode"
      :from-label="`${fromVersion?.version ?? state.from} · before`"
      :to-label="`${toVersion?.version ?? state.to} · after`"
    />

    <GovernCaveat tone="info" title="What this compares">
      Only instruction text is compared, section by section. Promotion safety comes from the checks and approvals on the
      Promotion tab, not from the size of this diff.
    </GovernCaveat>
  </div>
</template>
