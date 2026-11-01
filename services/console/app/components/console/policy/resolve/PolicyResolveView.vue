<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowRight, Play, Search, ShieldAlert, Workflow } from "@lucide/vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernActorBadge from "@/components/console/govern/primitives/GovernActorBadge.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernDecisionPill from "@/components/console/govern/primitives/GovernDecisionPill.vue"
import GovernEffectTag from "@/components/console/govern/primitives/GovernEffectTag.vue"
import GovernModeTag from "@/components/console/govern/primitives/GovernModeTag.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernTimeTravelPicker from "@/components/console/govern/primitives/GovernTimeTravelPicker.vue"
import { formatGovernNumber, formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import {
  POLICY_DECISION_LABELS,
  policyResolveAt,
  policyResolveRun,
  policyRunDecisions,
  policySnapshotAt,
  policySnapshots,
  policySnapshotState,
  type PolicyResolvedRule,
  type PolicyRunDecision,
} from "@/lib/policy-preview"
import { policyResolveHref, policyRuleDetailHref, policySnapshotHref, type PolicyResolveState } from "@/lib/govern-query"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"

const props = defineProps<{
  state: PolicyResolveState
  returnTo: string
}>()

const emit = defineEmits<{ update: [state: PolicyResolveState] }>()

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)
const runInput = ref(props.state.run)
const input = ref<HTMLInputElement | null>(null)

watch(
  () => props.state,
  (next) => {
    runInput.value = next.run
  },
)

const runResult = computed(() => (props.state.run ? policyResolveRun(props.state.run) : null))
const atResult = computed(() => (props.state.at ? policyResolveAt(props.state.at) : null))
const runNotFound = computed(() => Boolean(props.state.run) && !runResult.value)
const atNotFound = computed(() => Boolean(props.state.at) && !atResult.value)
const selectedSnapshotId = computed(() =>
  props.state.at ? (policySnapshotAt(props.state.at)?.id ?? "") : "",
)

const examples = computed(() => policyRunDecisions.slice(0, 4))

function submitRun(): void {
  const run = runInput.value.trim()
  if (!run) {
    input.value?.focus()
    return
  }
  emit("update", { run, at: "" })
}

function chooseSnapshot(snapshotId: string): void {
  const snapshot = policySnapshots.find((entry) => entry.id === snapshotId)
  if (!snapshot) return
  emit("update", { run: "", at: snapshot.effectiveFrom })
}

function clear(): void {
  runInput.value = ""
  emit("update", { run: "", at: "" })
}

function chooseRun(runId: string): void {
  runInput.value = runId
  emit("update", { run: runId, at: "" })
}

function statusLabel(entry: PolicyResolvedRule): string {
  if (entry.status === "not_evaluated") return "Not evaluated"
  if (!entry.decision) return "Matched"
  if (entry.decision.decision === "blocked") return "Matched · Blocked"
  if (entry.decision.decision === "approval") return "Matched · Asked a person"
  return `Matched · ${POLICY_DECISION_LABELS[entry.decision.decision]}`
}

function statusTone(entry: PolicyResolvedRule): string {
  if (entry.status === "not_evaluated") return "border-line-subtle bg-transparent text-fg-3"
  if (!entry.decision) return "border-line bg-raised text-fg-2"
  if (entry.decision.decision === "blocked") return "border-transparent bg-transparent text-crit"
  if (entry.decision.decision === "approval") return "border-transparent bg-transparent text-warn"
  return "border-accent/30 bg-accent-tint text-accent"
}

function evidenceLabel(decision: PolicyRunDecision): string {
  if (decision.evidence === "certified") return "Certified"
  if (decision.evidence === "sampled") return "Sampled"
  return "Not recorded"
}

const { helpOpen } = useGovernShortcuts({
  onSearch: () => input.value?.focus(),
  keys: {
    y: () => {
      if (!import.meta.client) return
      void navigator.clipboard?.writeText(`${window.location.origin}${policyResolveHref(props.state)}`)
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
            <h1 class="ix-page-title text-fg-1">Resolve a run</h1>
                      </div>
          <p class="mt-1 max-w-2xl text-sm leading-5 text-fg-2">
            See what a recorded run decided, or which rules were in force at a given moment.
          </p>
        </div>
        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip @open="about?.open()" />
    <GovernAboutPopover
      ref="about"
      verdict="Resolved runs and rule sets are illustrative fixtures joined from recorded preview decisions."
      contract="operator.decisions.list.v1"
      scope="org_demo_42 · workspace ws_42"
      range="Recorded decisions, 20–30 Oct 2026"
      coverage="Preview fixtures · no live decision store connected"
      phase="D5 · Phase B2"
      claim="No enforcement, audit, or billing claim."
      :notes="[
        { lead: 'Resolution is a join, not an evaluation.', body: 'This page shows the decision and rule revision that were recorded. It never re-evaluates conditions in the browser.' },
        { lead: 'Missing decisions stay missing.', body: 'A rule with no recorded decision is labelled Not evaluated instead of being inferred as passed.' },
        { lead: 'Retention is not reported yet.', body: 'Run retention needs the decision list contract; until then, an absent run is shown as not found without a retention claim.' },
      ]"
    />
          <NuxtLink to="/policies?tab=decisions" class="ix-button-secondary h-8 gap-1.5 px-2.5 text-xs">
            <Workflow :size="13" :stroke-width="1.8" aria-hidden="true" />
            Recorded decisions
          </NuxtLink>
        </div>
      </div>
    </header>

    <form
      class="grid gap-3 rounded-lg border border-line-subtle bg-surface-1 p-4 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]"
      @submit.prevent="submitRun"
    >
      <div class="flex min-w-0 flex-col gap-1.5">
        <label for="resolve-run" class="text-xs font-medium text-fg-2">Run ID</label>
        <div class="flex gap-2">
          <input
            id="resolve-run"
            ref="input"
            v-model="runInput"
            type="text"
            name="run"
            autocomplete="off"
            spellcheck="false"
            placeholder="run_77b031"
            class="ix-input h-9 min-w-0 flex-1 font-mono text-xs"
          >
          <button type="submit" class="ix-button-primary h-9 shrink-0 gap-1.5 px-3 text-xs">
            <Play :size="12" :stroke-width="2" aria-hidden="true" />
            Resolve
          </button>
        </div>
        <p class="text-[0.6875rem] leading-4 text-fg-3">
          A run appears only when it joins to a recorded policy decision.
        </p>
      </div>

      <div class="flex items-center justify-center lg:px-2">
        <span class="text-[0.6875rem] tracking-wide text-fg-3 uppercase">or</span>
      </div>

      <div class="flex min-w-0 flex-col gap-1.5">
        <span class="text-xs font-medium text-fg-2">Rules in force at a time</span>
        <div class="flex min-w-0 items-center">
          <GovernTimeTravelPicker
            :snapshots="policySnapshots"
            :model-value="selectedSnapshotId"
            label="Snapshot"
            @update:model-value="chooseSnapshot"
          />
        </div>
        <p class="text-[0.6875rem] leading-4 text-fg-3">
          Pick a recorded snapshot. The rule set in force at its effective time is shown.
        </p>
      </div>
    </form>

    <GovernCaveat v-if="state.run || state.at" tone="lock">
      Resolving reads recorded data only. It does not re-run the request or change any decision.
      <button type="button" class="ml-1 underline underline-offset-2 hover:text-fg-2" @click="clear">Clear</button>
    </GovernCaveat>

    <section
      v-if="runResult"
      class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1"
      aria-labelledby="resolve-run-result"
    >
      <header class="flex flex-wrap items-start justify-between gap-3 border-b border-line-subtle px-4 py-3">
        <div class="min-w-0">
          <p id="resolve-run-result" class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Recorded run</p>
          <div class="mt-1 flex flex-wrap items-center gap-2">
            <GovernCopyId :id="runResult.runId" label="Run ID" />
            <span class="text-fg-3" aria-hidden="true">·</span>
            <span class="text-xs text-fg-2" :title="formatGovernStamp(runResult.decision.at)">
              {{ formatGovernRelative(runResult.decision.at) }}
            </span>
            <span class="text-fg-3" aria-hidden="true">·</span>
            <NuxtLink :to="policySnapshotHref(runResult.snapshot.id)" class="ix-link font-mono text-[0.6875rem]">
              {{ runResult.snapshot.id }}
            </NuxtLink>
            <span class="text-[0.6875rem] text-fg-3">{{ policySnapshotState(runResult.snapshot.id) }}</span>
          </div>
        </div>
        <GovernDecisionPill :decision="runResult.decision.decision" />
      </header>

      <div class="grid gap-4 px-4 py-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <GovernActorBadge :name="runResult.decision.agent" type="service" :subline="`${runResult.decision.agent} ${runResult.decision.agentVersion}`" size="sm" />
            <span class="text-xs text-fg-3">matched</span>
            <NuxtLink
              :to="policyRuleDetailHref(runResult.decision.ruleId, { tab: 'overview', snapshot: runResult.snapshot.id, rev: runResult.decision.ruleRevision })"
              class="ix-link font-mono text-xs"
            >
              {{ runResult.decision.ruleId }}@{{ runResult.decision.ruleRevision }}
            </NuxtLink>
          </div>
          <p class="mt-2 max-w-[68ch] text-sm leading-6 text-fg-1">{{ runResult.decision.summary }}</p>
          <div class="mt-3 flex flex-wrap items-center gap-1.5">
            <GovernEffectTag :effect="runResult.decision.effect" />
            <span class="text-xs text-fg-3">·</span>
            <span class="text-xs text-fg-2">Evidence: {{ evidenceLabel(runResult.decision) }}</span>
            <span class="text-xs text-fg-3">·</span>
            <span class="text-xs" :class="runResult.decision.provenance === 'partial' ? 'text-warn' : 'text-fg-2'">
              Provenance: {{ runResult.decision.provenance }}
            </span>
          </div>
        </div>

        <dl class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line-subtle bg-line-subtle">
          <div class="bg-surface-1 px-3 py-2.5">
            <dt class="text-[0.6875rem] text-fg-3">Decision</dt>
            <dd class="mt-0.5 text-sm font-medium text-fg-1">{{ POLICY_DECISION_LABELS[runResult.decision.decision] }}</dd>
          </div>
          <div class="bg-surface-1 px-3 py-2.5">
            <dt class="text-[0.6875rem] text-fg-3">Rules evaluated</dt>
            <dd class="mt-0.5 text-sm font-medium text-fg-1">
              {{ formatGovernNumber(runResult.rules.filter((entry) => entry.status === "matched").length) }} of
              {{ formatGovernNumber(runResult.rules.length) }}
            </dd>
          </div>
          <div class="bg-surface-1 px-3 py-2.5">
            <dt class="text-[0.6875rem] text-fg-3">Snapshot</dt>
            <dd class="mt-0.5">
              <NuxtLink :to="policySnapshotHref(runResult.snapshot.id)" class="ix-link font-mono text-[0.6875rem] break-all">
                {{ runResult.snapshot.id }}
              </NuxtLink>
            </dd>
          </div>
          <div class="bg-surface-1 px-3 py-2.5">
            <dt class="text-[0.6875rem] text-fg-3">Evidence</dt>
            <dd class="mt-0.5 text-sm font-medium" :class="runResult.decision.provenance === 'partial' ? 'text-warn' : 'text-fg-1'">
              {{ evidenceLabel(runResult.decision) }}
            </dd>
          </div>
        </dl>
      </div>

      <div
        v-if="runResult.decision.approval"
        class="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line-subtle bg-surface-2/40 px-4 py-2 text-xs text-fg-2"
      >
        <span class="font-medium text-fg-1">Person's response</span>
        <span>
          {{ runResult.decision.approval.state === "granted" ? "Granted" : runResult.decision.approval.state === "denied" ? "Denied" : "Waiting on a person" }}
        </span>
        <span v-if="runResult.decision.approval.by">by {{ runResult.decision.approval.by }}</span>
        <span v-if="runResult.decision.approval.minutes !== null">
          waited {{ runResult.decision.approval.minutes }} min
        </span>
        <span v-if="runResult.decision.approval.state === 'pending'" class="text-warn">No decision has been recorded yet.</span>
      </div>

      <div class="border-t border-line-subtle">
        <p class="px-4 pt-3 text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">
          Rules in {{ runResult.snapshot.id }}
        </p>
        <div class="ix-scroll mt-2 overflow-x-auto">
          <table class="ix-agent-table" aria-label="Resolved rules">
            <thead>
              <tr>
                <th scope="col" class="w-10 text-right">#</th>
                <th scope="col">Rule</th>
                <th scope="col" class="w-28">Effect</th>
                <th scope="col" class="w-28">Mode</th>
                <th scope="col" class="w-20 text-right">Rev</th>
                <th scope="col" class="w-44">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(entry, position) in runResult.rules" :key="entry.rule.id">
                <td class="text-right font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ position + 1 }}</td>
                <td>
                  <NuxtLink
                    :to="policyRuleDetailHref(entry.rule.id, { tab: 'overview', snapshot: runResult.snapshot.id, rev: entry.revision.revision })"
                    class="text-[0.8125rem] font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline"
                  >
                    {{ entry.rule.label }}
                  </NuxtLink>
                  <span class="mt-0.5 block font-mono text-[0.625rem] text-fg-3">{{ entry.rule.id }}</span>
                </td>
                <td><GovernEffectTag :effect="entry.revision.effect" /></td>
                <td><GovernModeTag :mode="entry.revision.mode" /></td>
                <td class="text-right font-mono text-xs text-fg-2 tabular-nums">{{ entry.revision.revision }}</td>
                <td>
                  <span class="inline-flex h-6 items-center rounded-full border px-2 text-[0.6875rem] font-medium" :class="statusTone(entry)">
                    {{ statusLabel(entry) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="px-4 py-2 text-[0.6875rem] leading-4 text-fg-3">
          "Not evaluated" means no decision was recorded for that rule on this run. It does not mean the rule passed.
        </p>
      </div>
    </section>

    <section
      v-if="runNotFound"
      class="rounded-lg border border-line-subtle bg-surface-1 p-6"
      aria-labelledby="resolve-run-missing"
    >
      <div class="flex items-start gap-3">
        <ShieldAlert :size="18" :stroke-width="1.8" class="mt-0.5 shrink-0 text-warn" aria-hidden="true" />
        <div class="min-w-0">
          <h2 id="resolve-run-missing" class="text-sm font-semibold text-fg-1">Run not found in the recorded set</h2>
          <p class="mt-1 max-w-[70ch] text-sm leading-6 text-fg-3">
            <span class="font-mono text-fg-2">{{ state.run }}</span> does not join to a recorded policy decision.
            This console never reconstructs a decision from partial data, so nothing is shown for it.
          </p>
          <p class="mt-2 text-xs leading-5 text-fg-3">
            Run retention is not reported yet. Try a run recorded in the last few days.
          </p>
          <div class="mt-3 flex flex-wrap gap-1.5">
            <button
              v-for="run in examples.slice(0, 3)"
              :key="run.runId"
              type="button"
              class="ix-preview-chip font-mono hover:text-fg-1"
              @click="chooseRun(run.runId)"
            >
              {{ run.runId }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <section
      v-if="atResult"
      class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1"
      aria-labelledby="resolve-at-result"
    >
      <header class="flex flex-wrap items-start justify-between gap-3 border-b border-line-subtle px-4 py-3">
        <div class="min-w-0">
          <p id="resolve-at-result" class="text-[0.6875rem] font-medium tracking-wide text-fg-3 uppercase">Rules in force</p>
          <p class="mt-1 text-sm font-medium text-fg-1">{{ formatGovernStamp(state.at) }}</p>
        </div>
        <NuxtLink :to="policySnapshotHref(atResult.snapshot.id)" class="ix-link text-xs">
          {{ atResult.snapshot.id }} · {{ formatGovernStamp(atResult.snapshot.effectiveFrom) }}
        </NuxtLink>
      </header>

      <GovernCaveat tone="info" class="m-4">
        No run is selected, so no decision is reported. This is the rule set that was in force at the chosen time.
      </GovernCaveat>

      <div class="border-t border-line-subtle">
        <div class="ix-scroll overflow-x-auto">
          <table class="ix-agent-table" aria-label="Rules in force at the chosen time">
            <thead>
              <tr>
                <th scope="col" class="w-10 text-right">#</th>
                <th scope="col">Rule</th>
                <th scope="col" class="w-28">Effect</th>
                <th scope="col" class="w-28">Mode</th>
                <th scope="col" class="w-20 text-right">Rev</th>
                <th scope="col" class="w-44">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(entry, position) in atResult.rules" :key="entry.rule.id">
                <td class="text-right font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ position + 1 }}</td>
                <td>
                  <NuxtLink
                    :to="policyRuleDetailHref(entry.rule.id, { tab: 'overview', snapshot: atResult.snapshot.id, rev: entry.revision.revision })"
                    class="text-[0.8125rem] font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline"
                  >
                    {{ entry.rule.label }}
                  </NuxtLink>
                  <span class="mt-0.5 block font-mono text-[0.625rem] text-fg-3">{{ entry.rule.id }}</span>
                </td>
                <td><GovernEffectTag :effect="entry.revision.effect" /></td>
                <td><GovernModeTag :mode="entry.revision.mode" /></td>
                <td class="text-right font-mono text-xs text-fg-2 tabular-nums">{{ entry.revision.revision }}</td>
                <td>
                  <span class="inline-flex h-6 items-center rounded-full border px-2 text-[0.6875rem] font-medium" :class="statusTone(entry)">
                    Not evaluated
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section
      v-if="atNotFound"
      class="rounded-lg border border-line-subtle bg-surface-1 p-6"
      aria-labelledby="resolve-at-missing"
    >
      <h2 id="resolve-at-missing" class="text-sm font-semibold text-fg-1">No snapshot in force at that time</h2>
      <p class="mt-1 max-w-[70ch] text-sm leading-6 text-fg-3">
        The chosen time is before the oldest recorded snapshot. Snapshots are never extrapolated backwards.
      </p>
      <div class="mt-3 flex flex-wrap gap-1.5">
        <button
          v-for="snapshot in policySnapshots.slice(-2)"
          :key="`${snapshot.id}-at`"
          type="button"
          class="ix-preview-chip font-mono hover:text-fg-1"
          @click="chooseSnapshot(snapshot.id)"
        >
          {{ snapshot.id }} · {{ formatGovernStamp(snapshot.effectiveFrom) }}
        </button>
      </div>
    </section>

    <section
      v-if="!state.run && !state.at"
      class="grid gap-4 rounded-lg border border-line-subtle bg-surface-1 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
      aria-labelledby="resolve-examples"
    >
      <div>
        <h2 id="resolve-examples" class="flex items-center gap-1.5 text-sm font-semibold text-fg-1">
          <Search :size="14" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
          Try a recorded run
        </h2>
        <p class="mt-1 text-xs leading-5 text-fg-3">
          These runs are part of the preview fixture and each joins to one recorded decision.
        </p>
        <ul class="mt-3 divide-y divide-line-subtle rounded-lg border border-line-subtle">
          <li v-for="run in examples" :key="run.runId" class="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
            <button type="button" class="ix-link font-mono text-xs" @click="chooseRun(run.runId)">
              {{ run.runId }}
            </button>
            <span class="flex items-center gap-2 text-xs text-fg-3">
              <span>{{ run.agent }} {{ run.agentVersion }}</span>
              <GovernDecisionPill :decision="run.decision" />
            </span>
          </li>
        </ul>
      </div>
      <div>
        <h2 class="flex items-center gap-1.5 text-sm font-semibold text-fg-1">
          <ArrowRight :size="14" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
          Or resolve a moment
        </h2>
        <p class="mt-1 text-xs leading-5 text-fg-3">
          Pick a recorded snapshot boundary to see which rules were published and in force.
        </p>
        <ul class="mt-3 divide-y divide-line-subtle rounded-lg border border-line-subtle">
          <li
            v-for="snapshot in policySnapshots.slice(0, 3)"
            :key="`${snapshot.id}-moment`"
            class="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
          >
            <button type="button" class="ix-link text-xs" @click="chooseSnapshot(snapshot.id)">
              {{ snapshot.id }}
            </button>
            <span class="text-[0.6875rem] text-fg-3">{{ formatGovernStamp(snapshot.effectiveFrom) }}</span>
          </li>
        </ul>
      </div>
    </section>


    <GovernShortcutsDialog
      v-model:open="helpOpen"
      :groups="[
        { title: 'Navigate', rows: [
          { keys: 'g p', label: 'Go to policies' },
          { keys: 'g d', label: 'Go to drift' },
          { keys: 'g a', label: 'Go to audit log' },
        ] },
        { title: 'This page', rows: [
          { keys: '/', label: 'Focus the run input' },
          { keys: 'y', label: 'Copy resolve link' },
          { keys: '?', label: 'Show shortcuts' },
        ] },
      ]"
    />
  </div>
</template>
