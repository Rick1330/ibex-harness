<script setup lang="ts">
import { computed, ref } from "vue"
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  GitCompareArrows,
  Info,
  Plus,
  Radio,
} from "@lucide/vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"
import GovernDecisionPill from "@/components/console/govern/primitives/GovernDecisionPill.vue"
import GovernEffectTag from "@/components/console/govern/primitives/GovernEffectTag.vue"
import GovernEmptyValue from "@/components/console/govern/primitives/GovernEmptyValue.vue"
import GovernHashTag from "@/components/console/govern/primitives/GovernHashTag.vue"
import GovernImpactPlan from "@/components/console/govern/primitives/GovernImpactPlan.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernModeTag from "@/components/console/govern/primitives/GovernModeTag.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import PolicyLifecycleStepper from "./PolicyLifecycleStepper.vue"
import { formatGovernDuration, formatGovernNumber, formatGovernPercent, formatGovernRelative, formatGovernShortDate, formatGovernStamp } from "@/lib/govern-format"
import {
  policyImpact,
  policyProvenance,
  policyRawSnapshot,
  policyRulesForSnapshot,
  policySnapshotChangeSummary,
  policySnapshotJson,
  policySnapshotLifecycle,
  policySnapshotRuns,
  policySnapshotState,
  policySnapshots,
  type PolicySnapshot,
} from "@/lib/policy-preview"
import {
  POLICY_SNAPSHOT_TAB_LABELS,
  policyCompareHref,
  policyRuleDetailHref,
  policySnapshotHref,
  type PolicySnapshotDetailState,
  type PolicySnapshotTab,
} from "@/lib/govern-query"

const props = defineProps<{
  snapshot: PolicySnapshot
  state: PolicySnapshotDetailState
  returnTo: string
}>()

const emit = defineEmits<{ update: [state: PolicySnapshotDetailState] }>()

function selectTab(tab: PolicySnapshotTab): void {
  emit("update", { ...props.state, tab })
}

const index = computed(() => policySnapshots.findIndex((entry) => entry.id === props.snapshot.id))
const newer = computed(() => (index.value > 0 ? policySnapshots[index.value - 1]! : null))
const older = computed(() => (index.value >= 0 ? policySnapshots[index.value + 1] ?? null : null))

const stateLabel = computed(() => policySnapshotState(props.snapshot.id))
const changes = computed(() => policySnapshotChangeSummary(props.snapshot.id))
const rules = computed(() => policyRulesForSnapshot(props.snapshot.id))
const modeCounts = computed(() => ({
  enforced: rules.value.filter((entry) => entry.revision.mode === "enforced").length,
  advisory: rules.value.filter((entry) => entry.revision.mode === "advisory").length,
}))
const lifecycle = computed(() => policySnapshotLifecycle(props.snapshot.id))
const impact = computed(() => policyImpact(props.snapshot.id))
const provenance = computed(() => policyProvenance(props.snapshot.id))
const runs = computed(() =>
  policySnapshotRuns(props.snapshot.id).sort((left, right) => Date.parse(right.at) - Date.parse(left.at)),
)
const raw = computed(() => JSON.stringify(policySnapshotJson(props.snapshot.id), null, 2))

const tabs = [
  { id: "overview", label: POLICY_SNAPSHOT_TAB_LABELS.overview },
  { id: "rules", label: POLICY_SNAPSHOT_TAB_LABELS.rules },
  { id: "impact", label: POLICY_SNAPSHOT_TAB_LABELS.impact },
  { id: "runs", label: POLICY_SNAPSHOT_TAB_LABELS.runs },
  { id: "raw", label: POLICY_SNAPSHOT_TAB_LABELS.raw },
]

const compareHref = computed(() =>
  props.snapshot.previousId
    ? policyCompareHref({ from: props.snapshot.previousId, to: props.snapshot.id, hideUnchanged: false })
    : null,
)

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)
const copied = ref(false)

async function copyRaw(): Promise<void> {
  if (!import.meta.client) return
  try {
    await navigator.clipboard.writeText(raw.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 1_600)
  } catch {
    copied.value = false
  }
}

function ruleHref(ruleId: string): string {
  const href = policyRuleDetailHref(ruleId, { tab: "overview", snapshot: props.snapshot.id, rev: null })
  return `${href}?return=${encodeURIComponent(props.returnTo)}`
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <header class="min-w-0">
      <div class="flex items-center justify-between gap-3">
        <NuxtLink :to="returnTo" class="inline-flex items-center gap-1.5 rounded text-xs text-fg-3 transition-colors hover:text-fg-1">
          <ChevronLeft :size="13" :stroke-width="1.9" aria-hidden="true" />
          Back to policies
        </NuxtLink>
        <div class="flex items-center gap-0.5">
          <NuxtLink
            v-if="newer"
            :to="policySnapshotHref(newer.id)"
            class="inline-flex h-7 items-center gap-1 rounded px-1.5 text-[0.6875rem] text-fg-3 hover:bg-raised hover:text-fg-1"
            :aria-label="`Newer snapshot ${newer.id}`"
          >
            <ChevronLeft :size="12" :stroke-width="2" aria-hidden="true" /> Newer
          </NuxtLink>
          <NuxtLink
            v-if="older"
            :to="policySnapshotHref(older.id)"
            class="inline-flex h-7 items-center gap-1 rounded px-1.5 text-[0.6875rem] text-fg-3 hover:bg-raised hover:text-fg-1"
            :aria-label="`Older snapshot ${older.id}`"
          >
            Older <ChevronRight :size="12" :stroke-width="2" aria-hidden="true" />
          </NuxtLink>
        </div>
      </div>

      <div class="mt-3.5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <h1 class="font-mono ix-page-title text-fg-1">{{ snapshot.id }}</h1>
            <span
              class="inline-flex h-5.5 items-center gap-1 rounded-full border px-2 text-xs leading-none font-medium"
              :class="stateLabel === 'live' ? 'border-transparent bg-transparent text-ok' : 'border-line bg-raised text-fg-2'"
            >
              <Radio :size="10" :stroke-width="2.2" aria-hidden="true" />
              {{ stateLabel === "live" ? "Live" : "Superseded" }}
            </span>
            <GovernCopyId :id="snapshot.id" label="Snapshot ID" icon-only />
            <GovernHashTag :hash="snapshot.digest" label="snapshot digest" />
          </div>
          <p class="mt-1 max-w-3xl text-sm leading-5 text-fg-2">{{ snapshot.message }}</p>
          <p class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3">
            <span>Effective {{ formatGovernStamp(snapshot.effectiveFrom) }}</span>
            <span aria-hidden="true">·</span>
            <span>Published {{ formatGovernStamp(snapshot.publishedAt) }} by {{ snapshot.publishedBy }}</span>
            <span aria-hidden="true">·</span>
            <span class="font-mono">{{ rules.length }} rules</span>
          </p>
          <p v-if="snapshot.metadataNote" class="mt-2 inline-flex items-start gap-1.5 rounded-md border border-line-subtle bg-surface-2 px-2 py-1 text-xs leading-5 text-fg-2">
            <Info :size="12" :stroke-width="1.9" class="mt-1 shrink-0 text-fg-3" aria-hidden="true" />
            <span class="text-fg-2">{{ snapshot.metadataNote }}</span>
          </p>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <GovernDataSourceChip :live="false" @open="about?.open()" />
    <GovernAboutPopover
      ref="about"
      :verdict="`Snapshot ${snapshot.id} is shown as published. Rule bytes, lifecycle, and simulation values are illustrative fixtures; no live policy read model is connected.`"
      contract="operator.policies.snapshots.v1"
      scope="org_demo_42 · workspace ws_42"
      :range="`${formatGovernShortDate(snapshot.effectiveFrom)} · ${snapshot.id}`"
      coverage="Preview fixtures · no policy read model connected"
      phase="D5 · Phase B2"
      claim="No enforcement, audit, or billing claim."
    />
          <NuxtLink v-if="compareHref" :to="compareHref" class="ix-button-secondary h-8 gap-1.5 px-2.5 text-xs">
            <GitCompareArrows :size="13" :stroke-width="1.8" aria-hidden="true" />
            Compare with previous
          </NuxtLink>
          <GovernLockedAction label="New snapshot" :icon="Plus" variant="primary" />
        </div>
      </div>
    </header>

    <GovernCaveat v-if="changes.metadataOnly" tone="info" title="No rule bytes changed.">
      Every rule in this snapshot is identical to {{ snapshot.previousId }}; only the release note differs.
    </GovernCaveat>

    <div class="grid grid-cols-2 gap-2 sm:gap-3 xl:grid-cols-4">
      <GovernStatTile label="Rules in force" :value="String(rules.length)" :helper="`${modeCounts.enforced} enforced · ${modeCounts.advisory} advisory`" compact />
      <GovernStatTile label="Rules changed" :value="String(changes.changed)" :helper="changes.changed === 0 ? 'No rule bytes changed' : changes.names.join(', ')" compact />
      <GovernStatTile label="Linked runs" :value="formatGovernNumber(provenance.linked)" :helper="`${provenance.complete} certified · ${provenance.partial} partial`" :tone="provenance.partial > 0 ? 'warning' : 'default'" compact />
      <GovernStatTile label="Live for" :value="stateLabel === 'live' ? formatGovernDuration(snapshot.effectiveFrom, null) : 'Superseded'" :helper="stateLabel === 'live' ? 'Current runtime snapshot' : `Replaced by ${newer?.id ?? 'a newer snapshot'}`" compact />
    </div>

    <GovernTabBar
      :tabs="tabs"
      :model-value="state.tab"
      aria-label="Snapshot views"
      @update:model-value="selectTab($event as PolicySnapshotTab)"
    />

    <div class="min-w-0">
      <div v-if="state.tab === 'overview'" class="flex flex-col gap-3">
        <section class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="snapshot-lifecycle">
          <header class="border-b border-line-subtle px-4 py-2.5">
            <h2 id="snapshot-lifecycle" class="text-sm font-semibold text-fg-1">How this snapshot was published</h2>
            <p class="mt-0.5 text-xs text-fg-3">Drafted → Validated → Simulated → Approved → Live</p>
          </header>
          <div class="px-4 py-3">
            <PolicyLifecycleStepper :steps="lifecycle" />
          </div>
        </section>

        <div class="grid gap-3 lg:grid-cols-2">
          <section class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="snapshot-changes">
            <header class="border-b border-line-subtle px-4 py-2.5">
              <h2 id="snapshot-changes" class="text-sm font-semibold text-fg-1">What changed</h2>
              <p class="mt-0.5 text-xs text-fg-3">Compared with {{ snapshot.previousId ?? "no earlier snapshot" }}</p>
            </header>
            <div class="px-4 py-3">
              <p class="text-sm leading-6 text-fg-1">
                <template v-if="changes.metadataOnly">{{ changes.reason }}</template>
                <template v-else-if="changes.changed === 0">No rule changed in this snapshot.</template>
                <template v-else>{{ changes.changed }} rules changed: {{ changes.names.join(", ") }}.</template>
              </p>
              <ul v-if="changes.names.length" class="mt-2 flex flex-wrap gap-1.5">
                <li v-for="name in changes.names" :key="name" class="ix-preview-chip">{{ name }}</li>
              </ul>
            </div>
          </section>

          <section class="rounded-lg border border-line-subtle bg-surface-1" aria-labelledby="snapshot-facts">
            <header class="border-b border-line-subtle px-4 py-2.5">
              <h2 id="snapshot-facts" class="text-sm font-semibold text-fg-1">Snapshot facts</h2>
            </header>
            <dl class="divide-y divide-line-subtle">
              <div class="flex items-baseline justify-between gap-3 px-4 py-2">
                <dt class="text-xs text-fg-3">Effective from</dt>
                <dd class="text-xs text-fg-1">{{ formatGovernStamp(snapshot.effectiveFrom) }}</dd>
              </div>
              <div class="flex items-baseline justify-between gap-3 px-4 py-2">
                <dt class="text-xs text-fg-3">Published at</dt>
                <dd class="text-xs text-fg-1">{{ formatGovernStamp(snapshot.publishedAt) }}</dd>
              </div>
              <div class="flex items-baseline justify-between gap-3 px-4 py-2">
                <dt class="text-xs text-fg-3">Published by</dt>
                <dd class="text-xs text-fg-1">{{ snapshot.publishedBy }}</dd>
              </div>
              <div class="flex items-baseline justify-between gap-3 px-4 py-2">
                <dt class="text-xs text-fg-3">Previous snapshot</dt>
                <dd>
                  <NuxtLink v-if="snapshot.previousId" :to="policySnapshotHref(snapshot.previousId)" class="font-mono text-[0.6875rem] text-fg-2 underline decoration-line-strong underline-offset-2 hover:text-fg-1">
                    {{ snapshot.previousId }}
                  </NuxtLink>
                  <span v-else class="text-xs text-fg-3">First snapshot</span>
                </dd>
              </div>
              <div class="flex items-baseline justify-between gap-3 px-4 py-2">
                <dt class="text-xs text-fg-3">Digest</dt>
                <dd><GovernHashTag :hash="snapshot.digest" label="snapshot digest" /></dd>
              </div>
            </dl>
          </section>
        </div>

        <GovernCaveat v-if="provenance.partial > 0" tone="warning" title="Partial provenance.">
          {{ provenance.partial }} of {{ provenance.linked }} linked runs in this snapshot do not join to a certified evidence record. Fire counts on the rules page may be low for that reason.
        </GovernCaveat>
      </div>

      <div v-else-if="state.tab === 'rules'" class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
        <div class="ix-scroll overflow-x-auto">
          <table class="ix-agent-table" aria-label="Rules in this snapshot">
            <thead>
              <tr>
                <th scope="col" class="min-w-56">Rule</th>
                <th scope="col" class="w-24">Area</th>
                <th scope="col" class="w-32">Effect</th>
                <th scope="col" class="hidden w-28 min-[1100px]:table-cell">Mode</th>
                <th scope="col" class="w-32 text-right">Fired 7d</th>
                <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rule in rules" :key="rule.id">
                <td>
                  <NuxtLink :to="ruleHref(rule.id)" class="block max-w-72 truncate text-[0.8125rem] font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline">
                    {{ rule.label }}
                  </NuxtLink>
                  <span class="mt-0.5 block truncate font-mono text-[0.625rem] text-fg-3">{{ rule.id }}@{{ rule.revision.revision }}</span>
                </td>
                <td><span class="text-xs text-fg-2">{{ rule.area }}</span></td>
                <td><GovernEffectTag :effect="rule.revision.effect" :title="rule.revision.condition" /></td>
                <td class="hidden min-[1100px]:table-cell"><GovernModeTag :mode="rule.revision.mode" /></td>
                <td class="text-right">
                  <span v-if="rule.fired !== null" class="font-mono text-xs text-fg-2 tabular-nums">{{ formatGovernNumber(rule.fired) }}</span>
                  <GovernEmptyValue v-else reason="No decision data joined for this rule" />
                </td>
                <td>
                  <NuxtLink :to="ruleHref(rule.id)" class="inline-flex size-6 items-center justify-center rounded text-fg-3 hover:bg-raised hover:text-fg-1" :aria-label="`Open ${rule.label}`">
                    <ChevronRight :size="14" :stroke-width="1.9" aria-hidden="true" />
                  </NuxtLink>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="state.tab === 'impact'" class="flex flex-col gap-3">
        <GovernCaveat tone="info">
          Replay of recorded decisions against this snapshot. The simulation endpoint replays history; it does not forecast production traffic.
        </GovernCaveat>
        <GovernImpactPlan :impact="impact" />
        <p class="text-xs leading-5 text-fg-2">
          <span class="font-medium text-fg-1">{{ formatGovernNumber(impact.changed) }} of {{ formatGovernNumber(impact.replayed) }}</span>
          replayed decisions would change ({{ formatGovernPercent(impact.replayed > 0 ? (impact.changed / impact.replayed) * 100 : 0, 1) }}).
        </p>
      </div>

      <div v-else-if="state.tab === 'runs'" class="flex flex-col gap-3">
        <div v-if="runs.length === 0" class="rounded-lg border border-dashed border-line-subtle bg-surface-1/40 px-4 py-8 text-center text-xs text-fg-3">
          No linked runs for this snapshot.
        </div>
        <div v-else class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
          <div class="ix-scroll overflow-x-auto">
            <table class="ix-agent-table" aria-label="Runs in this snapshot">
              <thead>
                <tr>
                  <th scope="col" class="w-32">Time</th>
                  <th scope="col" class="min-w-40">Run</th>
                  <th scope="col" class="hidden w-40 min-[900px]:table-cell">Agent</th>
                  <th scope="col" class="min-w-44">Rule</th>
                  <th scope="col" class="w-32">Decision</th>
                  <th scope="col" class="hidden w-28 min-[1260px]:table-cell">Provenance</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="run in runs" :key="run.runId + run.ruleId">
                  <td><span class="text-xs text-fg-2" :title="formatGovernStamp(run.at)">{{ formatGovernRelative(run.at) }}</span></td>
                  <td><span class="font-mono text-[0.6875rem] text-fg-1">{{ run.runId }}</span></td>
                  <td class="hidden min-[900px]:table-cell">
                    <span class="block text-xs text-fg-2">{{ run.agent }}</span>
                    <span class="block font-mono text-[0.625rem] text-fg-3">{{ run.agentVersion }}</span>
                  </td>
                  <td>
                    <NuxtLink :to="ruleHref(run.ruleId)" class="text-xs text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline">
                      {{ run.ruleId }}@{{ run.ruleRevision }}
                    </NuxtLink>
                  </td>
                  <td><GovernDecisionPill :decision="run.decision" /></td>
                  <td class="hidden min-[1260px]:table-cell">
                    <span class="text-xs" :class="run.provenance === 'partial' ? 'text-warn' : 'text-fg-2'">{{ run.provenance === "partial" ? "Partial" : "Complete" }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-else class="flex flex-col gap-2">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <p class="text-xs text-fg-3">The raw snapshot payload as published. This is the contract body, not a rendering.</p>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-subtle bg-surface-1 px-2.5 text-xs text-fg-2 transition-colors hover:border-line hover:text-fg-1"
            @click="copyRaw"
          >
            <Check v-if="copied" :size="12" :stroke-width="2.2" class="text-ok" aria-hidden="true" />
            <Copy v-else :size="12" :stroke-width="1.8" aria-hidden="true" />
            {{ copied ? "Copied" : "Copy JSON" }}
          </button>
        </div>
        <pre class="ix-scroll max-h-[38rem] overflow-auto rounded-lg border border-line-subtle bg-surface-1 px-4 py-3 font-mono text-[0.6875rem] leading-5 text-fg-2" aria-label="Raw snapshot JSON">{{ raw }}</pre>
        <p class="font-mono text-[0.625rem] text-fg-3">{{ policyRawSnapshot(snapshot.id).length }} rules · digest {{ snapshot.digest.slice(0, 19) }}…</p>
      </div>
    </div>

  </div>
</template>
