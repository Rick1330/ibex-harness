<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowLeftRight, ChevronDown, GitCompareArrows } from "@lucide/vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernDiffSummaryBar from "@/components/console/govern/primitives/GovernDiffSummaryBar.vue"
import GovernEffectTag from "@/components/console/govern/primitives/GovernEffectTag.vue"
import GovernModeTag from "@/components/console/govern/primitives/GovernModeTag.vue"
import GovernSectionDiff from "@/components/console/govern/primitives/GovernSectionDiff.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import { diffSummary } from "@/lib/govern-diff"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import {
  policyCompare,
  policySnapshotState,
  policySnapshots,
  type PolicyCompareRule,
  type PolicyCompareStatus,
} from "@/lib/policy-preview"
import {
  policyCompareHref,
  policyRuleDetailHref,
  policySnapshotHref,
  swapPolicyCompare,
  type PolicyCompareState,
} from "@/lib/govern-query"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"

const props = defineProps<{
  state: PolicyCompareState
  returnTo: string
}>()

const emit = defineEmits<{ update: [state: PolicyCompareState] }>()

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)
const result = computed(() => policyCompare(props.state.from, props.state.to))
const sameSnapshot = computed(() => props.state.from === props.state.to)

const toSummary = computed(() =>
  result.value?.to.metadataNote
    ? { text: `${result.value.to.id} is metadata only.`, detail: result.value.to.metadataNote }
    : null,
)

function setSide(side: "from" | "to", snapshotId: string): void {
  emit("update", { ...props.state, [side]: snapshotId })
}

function swap(): void {
  emit("update", swapPolicyCompare(props.state))
}

function toggleHideUnchanged(): void {
  emit("update", { ...props.state, hideUnchanged: !props.state.hideUnchanged })
}

function statusLabel(status: PolicyCompareStatus): string {
  if (status === "changed") return "Changed"
  if (status === "added") return "Added"
  if (status === "removed") return "Removed"
  return "Unchanged"
}

function ruleHref(entry: PolicyCompareRule): string {
  const snapshotId = entry.status === "removed" ? props.state.from : props.state.to
  return policyRuleDetailHref(entry.rule.id, { tab: "overview", snapshot: snapshotId, rev: null })
}

function revisionLabel(entry: PolicyCompareRule, side: "from" | "to"): string {
  const revision = side === "from" ? entry.fromRevision : entry.toRevision
  return revision ? `@${revision.revision}` : "—"
}

const { helpOpen } = useGovernShortcuts({
  keys: {
    y: () => {
      if (!import.meta.client) return
      void navigator.clipboard?.writeText(`${window.location.origin}${policyCompareHref(props.state)}`)
    },
  },
})
</script>

<template>
  <div class="mx-auto flex w-full max-w-[90rem] flex-col gap-4">

    <header class="flex flex-col gap-3">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <NuxtLink :to="returnTo" class="text-xs text-fg-3 hover:text-fg-1">← Back to policies</NuxtLink>
          <div class="mt-1 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <h1 class="ix-page-title text-fg-1">Compare snapshots</h1>
                      </div>
          <p class="mt-1 max-w-2xl text-sm leading-5 text-fg-2">
            Two recorded snapshots, compared rule by rule. A missing revision means the rule was not published on
            that side, not that it was deleted at runtime.
          </p>
        </div>
        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip @open="about?.open()" />
    <GovernAboutPopover
      ref="about"
      verdict="Both sides of this comparison are illustrative snapshot fixtures. No live policy read model is connected."
      contract="operator.policies.snapshots.v1"
      scope="org_demo_42 · workspace ws_42"
      range="Four illustrative snapshots, 11–27 Oct 2026"
      coverage="Preview fixtures · differences computed from recorded rule revisions only"
      phase="D5 · Phase B2"
      claim="No enforcement, audit, or billing claim."
      :notes="[
        { lead: 'Snapshots are immutable.', body: 'A rule difference means the revision number changed between the two snapshots. Nothing is inferred about runtime behaviour.' },
        { lead: 'Unchanged means identical revision.', body: 'Rules are collapsed only when both snapshots publish the same revision number.' },
        { lead: 'Metadata-only snapshots are labelled.', body: 'A snapshot published to correct a release note keeps the same rule bytes and says so before any diff is read.' },
      ]"
    />
          <NuxtLink to="/policies?tab=rules" class="ix-button-secondary h-8 gap-1.5 px-2.5 text-xs">
            <GitCompareArrows :size="13" :stroke-width="1.8" aria-hidden="true" />
            Rules in force
          </NuxtLink>
        </div>
      </div>
    </header>

    <section
      class="grid gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]"
      aria-label="Snapshot pair"
    >
      <label class="flex min-w-0 flex-col gap-1 bg-surface-1 px-4 py-3">
        <span class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Compared from</span>
        <select
          :value="state.from"
          class="mt-0.5 h-8 w-full min-w-0 rounded-md border border-line bg-raised px-2 font-mono text-xs text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
          aria-label="Snapshot from"
          @change="setSide('from', ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="snapshot in policySnapshots" :key="snapshot.id" :value="snapshot.id">
            {{ snapshot.id }} · {{ policySnapshotState(snapshot.id) }}
          </option>
        </select>
        <p v-if="result" class="text-[0.625rem] leading-4 text-fg-3">
          Effective {{ formatGovernStamp(result.from.effectiveFrom) }}
        </p>
      </label>
      <div class="flex items-center justify-center bg-surface-1 px-2 py-3">
        <button
          type="button"
          class="inline-flex size-8 items-center justify-center rounded-md border border-line text-fg-2 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
          aria-label="Swap compared snapshots"
          @click="swap"
        >
          <ArrowLeftRight :size="14" :stroke-width="1.8" aria-hidden="true" />
        </button>
      </div>
      <label class="flex min-w-0 flex-col gap-1 bg-surface-1 px-4 py-3">
        <span class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Compared to</span>
        <select
          :value="state.to"
          class="mt-0.5 h-8 w-full min-w-0 rounded-md border border-line bg-raised px-2 font-mono text-xs text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
          aria-label="Snapshot to"
          @change="setSide('to', ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="snapshot in policySnapshots" :key="snapshot.id" :value="snapshot.id">
            {{ snapshot.id }} · {{ policySnapshotState(snapshot.id) }}
          </option>
        </select>
        <p v-if="result" class="text-[0.625rem] leading-4 text-fg-3">
          Effective {{ formatGovernStamp(result.to.effectiveFrom) }} · {{ result.rules.length }} rules
        </p>
      </label>
    </section>

    <GovernCaveat v-if="sameSnapshot" tone="warning" title="The same snapshot is selected twice.">
      Every rule is unchanged. Pick two different snapshots to see what moved between them.
    </GovernCaveat>

    <GovernCaveat v-if="toSummary" tone="info" :title="toSummary.text">{{ toSummary.detail }}</GovernCaveat>

    <section
      v-if="result"
      class="grid gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle sm:grid-cols-4"
      aria-label="Comparison summary"
    >
      <div
        v-for="tile in [
          { label: 'Rules changed', value: result.changed, tone: result.changed > 0 ? 'text-warn' : 'text-fg-1' },
          { label: 'Rules added', value: result.added, tone: 'text-fg-1' },
          { label: 'Rules removed', value: result.removed, tone: 'text-fg-1' },
          { label: 'Unchanged', value: result.unchanged, tone: 'text-fg-1' },
        ]"
        :key="tile.label"
        class="bg-surface-1 px-4 py-3"
      >
        <p class="text-[0.6875rem] text-fg-3">{{ tile.label }}</p>
        <p class="mt-0.5 font-mono text-lg leading-6 tabular-nums" :class="tile.tone">
          {{ formatGovernNumber(tile.value) }}
        </p>
      </div>
    </section>

    <template v-if="result">
      <p v-if="result.changed + result.added + result.removed === 0" class="text-sm text-fg-3">
        No rule differences between {{ result.from.id }} and {{ result.to.id }}.
      </p>

      <article
        v-for="entry in result.rules.filter((rule) => rule.status !== 'unchanged')"
        :key="entry.rule.id"
        class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1"
      >
        <header class="flex flex-wrap items-start justify-between gap-3 border-b border-line-subtle px-4 py-3">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <NuxtLink
                :to="ruleHref(entry)"
                class="text-sm font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline"
              >
                {{ entry.rule.label }}
              </NuxtLink>
              <span
                class="rounded-full border px-2 py-0.5 text-[0.6875rem] font-medium"
                :class="entry.status === 'changed' ? 'border-transparent bg-transparent text-warn' : 'border-line bg-raised text-fg-2'"
              >
                {{ statusLabel(entry.status) }}
              </span>
            </div>
            <p class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[0.6875rem] text-fg-3">
              <span>{{ entry.rule.id }}{{ revisionLabel(entry, "from") }}</span>
              <span aria-hidden="true">→</span>
              <span>{{ entry.rule.id }}{{ revisionLabel(entry, "to") }}</span>
              <span aria-hidden="true">·</span>
              <span>{{ entry.rule.area }} · {{ entry.rule.scope }}</span>
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-1.5">
            <GovernEffectTag v-if="entry.toRevision" :effect="entry.toRevision.effect" />
            <GovernModeTag v-if="entry.toRevision" :mode="entry.toRevision.mode" />
            <span v-if="!entry.toRevision && entry.fromRevision" class="text-xs text-fg-3">
              Last published as {{ entry.fromRevision.effect }}
            </span>
          </div>
        </header>

        <div class="flex flex-wrap items-center gap-1.5 border-b border-line-subtle bg-surface-2/40 px-4 py-2 text-xs text-fg-3">
          <template v-if="entry.toRevision">
            <span>Changed by {{ entry.toRevision.changedBy }}</span>
            <span aria-hidden="true">·</span>
            <span>{{ formatGovernStamp(entry.toRevision.effectiveFrom) }}</span>
            <span aria-hidden="true">·</span>
            <span class="min-w-0">{{ entry.toRevision.changeSummary }}</span>
          </template>
          <template v-else>
            <span>Last published by {{ entry.fromRevision?.changedBy }}</span>
            <span aria-hidden="true">·</span>
            <span>{{ entry.fromRevision ? formatGovernStamp(entry.fromRevision.effectiveFrom) : "" }}</span>
            <span aria-hidden="true">·</span>
            <span>Not present in {{ result.to.id }}.</span>
          </template>
        </div>

        <div class="px-4 py-3">
          <GovernCaveat
            v-if="entry.status === 'changed' && entry.changedKeys.length === 0"
            tone="warning"
            title="The rule bytes changed outside the fields this console renders."
          >
            {{ entry.toRevision?.changeSummary }} The revision moved from
            {{ revisionLabel(entry, "from") }} to {{ revisionLabel(entry, "to") }}, so the rule is not shown as
            unchanged.
          </GovernCaveat>
          <template v-else>
            <div class="flex flex-wrap items-center justify-between gap-2">
              <GovernDiffSummaryBar
                :summary="diffSummary(entry.sections)"
                :from="revisionLabel(entry, 'from')"
                :to="revisionLabel(entry, 'to')"
                compact
              />
              <span v-if="entry.changedKeys.length" class="text-[0.6875rem] text-fg-3">
                Changed keys: {{ entry.changedKeys.join(", ") }}
              </span>
            </div>
            <div class="mt-2">
              <GovernSectionDiff :sections="entry.sections" mode="unified" />
            </div>
          </template>
        </div>

        <footer class="flex flex-wrap items-center justify-between gap-2 border-t border-line-subtle px-4 py-2">
          <NuxtLink :to="ruleHref(entry)" class="ix-link text-xs">Open {{ entry.rule.id }}</NuxtLink>
          <NuxtLink
            :to="policySnapshotHref(entry.status === 'removed' ? result.from.id : result.to.id, { tab: 'raw' })"
            class="text-xs text-fg-3 underline-offset-2 hover:text-fg-1 hover:underline"
          >
            Raw snapshot
          </NuxtLink>
        </footer>
      </article>

      <details
        v-if="result.unchanged > 0 && !state.hideUnchanged"
        class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1"
      >
        <summary class="flex cursor-pointer items-center justify-between gap-2 px-4 py-3 text-xs text-fg-2">
          <span class="flex items-center gap-1.5">
            <ChevronDown :size="13" :stroke-width="1.8" aria-hidden="true" />
            {{ formatGovernNumber(result.unchanged) }} unchanged
            {{ result.unchanged === 1 ? "rule" : "rules" }}
          </span>
          <span class="text-fg-3">No byte difference between the two snapshots.</span>
        </summary>
        <ul class="divide-y divide-line-subtle border-t border-line-subtle">
          <li
            v-for="entry in result.rules.filter((rule) => rule.status === 'unchanged')"
            :key="entry.rule.id"
            class="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-xs"
          >
            <NuxtLink :to="ruleHref(entry)" class="ix-link">{{ entry.rule.label }}</NuxtLink>
            <span class="font-mono text-[0.6875rem] text-fg-3">
              {{ entry.rule.id }}@{{ entry.toRevision?.revision }} · {{ entry.rule.area }}
            </span>
          </li>
        </ul>
      </details>

      <button
        v-if="result.unchanged > 0"
        type="button"
        class="self-start text-xs text-fg-3 underline-offset-2 hover:text-fg-1 hover:underline"
        @click="toggleHideUnchanged"
      >
        {{ state.hideUnchanged ? `Show ${formatGovernNumber(result.unchanged)} unchanged rules` : "Hide unchanged rules" }}
      </button>
    </template>


    <GovernShortcutsDialog
      v-model:open="helpOpen"
      :groups="[
        { title: 'Navigate', rows: [
          { keys: 'g p', label: 'Go to policies' },
          { keys: 'g d', label: 'Go to drift' },
          { keys: 'g a', label: 'Go to audit log' },
        ] },
        { title: 'This page', rows: [
          { keys: 'y', label: 'Copy comparison link' },
          { keys: '?', label: 'Show shortcuts' },
        ] },
      ]"
    />
  </div>
</template>
