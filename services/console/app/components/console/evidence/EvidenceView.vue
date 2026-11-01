<script setup lang="ts">
import { computed, ref } from "vue"
import EvidenceChainPanel from "./EvidenceChainPanel.vue"
import EvidenceHeader from "./EvidenceHeader.vue"
import EvidenceLedgerPanel from "./EvidenceLedgerPanel.vue"
import EvidenceRedactionPanel from "./EvidenceRedactionPanel.vue"
import EvidenceTombstonePanel from "./EvidenceTombstonePanel.vue"
import GovernFilterBar from "@/components/console/govern/primitives/GovernFilterBar.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { formatGovernRelative } from "@/lib/govern-format"
import {
  EVIDENCE_LIST_DEFAULT,
  EVIDENCE_TAB_LABELS,
  evidenceHref,
  type EvidenceListState,
  type EvidenceTab,
} from "@/lib/govern-query"
import {
  CHAIN_STATE_LABELS,
  CHAIN_STATES,
  DELETION_BASES,
  DELETION_BASIS_LABELS,
  EVIDENCE_PRODUCERS,
  EVIDENCE_REDACTION_ROWS,
  EVIDENCE_SUMMARY_CONTRACT,
  chainStateCounts,
  evidenceChainInRange,
  evidenceProducersFor,
  evidenceTombstonesInRange,
  filterChainLinks,
  filterEvidenceProducers,
  filterEvidenceRedaction,
  filterTombstones,
  tombstoneChainComplete,
  type ChainState,
  type DeletionBasis,
  type EvidenceRange,
} from "@/lib/evidence-preview"

const props = defineProps<{ state: EvidenceListState }>()
const emit = defineEmits<{ update: [state: EvidenceListState] }>()

function update(patch: Partial<EvidenceListState>): void {
  emit("update", { ...props.state, ...patch })
}

const header = ref<InstanceType<typeof EvidenceHeader> | null>(null)
const search = ref<InstanceType<typeof GovernFilterBar> | null>(null)

const producers = computed(() => evidenceProducersFor(props.state.range))
const tombstones = computed(() => evidenceTombstonesInRange(props.state.range))
const chain = computed(() => evidenceChainInRange(props.state.range))
const redaction = computed(() => filterEvidenceRedaction(EVIDENCE_REDACTION_ROWS, props.state.q))

const ledgerRows = computed(() => filterEvidenceProducers(producers.value, props.state))
const tombstoneRows = computed(() => filterTombstones(tombstones.value, props.state))
const chainRows = computed(() => filterChainLinks(chain.value, props.state))
const chainCounts = computed(() => chainStateCounts(chain.value))

const tabs = [
  { id: "ledger", label: EVIDENCE_TAB_LABELS.ledger },
  { id: "tombstones", label: EVIDENCE_TAB_LABELS.tombstones },
  { id: "chain", label: EVIDENCE_TAB_LABELS.chain },
  { id: "redaction", label: EVIDENCE_TAB_LABELS.redaction },
]

const tabBadges = computed(() => ({
  ledger: String(ledgerRows.value.length),
  tombstones: String(tombstoneRows.value.length),
  chain: String(chainRows.value.length),
  redaction: String(redaction.value.length),
}))

const componentOptions = [
  { value: "all", label: "All producers" },
  ...EVIDENCE_PRODUCERS.map((row) => ({ value: row.id, label: row.label })),
]

const basisOptions = [
  { value: "all", label: "All bases" },
  ...DELETION_BASES.map((basis) => ({ value: basis, label: DELETION_BASIS_LABELS[basis] })),
]

const chainStateOptions = [
  { value: "all", label: "All states" },
  ...CHAIN_STATES.map((state) => ({ value: state, label: CHAIN_STATE_LABELS[state] })),
]

const placeholders: Record<EvidenceTab, string> = {
  ledger: "Filter producers: memory, relay, projection",
  tombstones: "Filter deletions: record id, basis, requester",
  chain: "Filter the chain: outbox id, producer, subject",
  redaction: "Filter pipelines: sanitizer, proof, removed field",
}

const openChain = computed(() => chainCounts.value.poison + chainCounts.value.gap + chainCounts.value.retrying)
const incompleteTombstones = computed(() => tombstones.value.filter((row) => !tombstoneChainComplete(row)).length)
const newestEvidence = computed(() => {
  const stamps = producers.value
    .map((row) => row.lastEvidenceAt)
    .filter((value): value is string => value !== null)
    .sort((left, right) => Date.parse(right) - Date.parse(left))
  return stamps[0] ?? null
})

const activeFilters = computed(
  () =>
    [
      props.state.q.trim() !== "",
      props.state.component !== "all",
      props.state.basis !== "all",
      props.state.chainState !== "all",
    ].filter(Boolean).length,
)

function clearFilters(): void {
  emit("update", { ...EVIDENCE_LIST_DEFAULT, tab: props.state.tab, range: props.state.range })
}

function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(`${window.location.origin}${evidenceHref(props.state)}`)
}

const { helpOpen } = useGovernShortcuts({
  onSearch: () => search.value?.focus(),
  keys: {
    y: copyCurrentLink,
    "1": () => update({ tab: "ledger" }),
    "2": () => update({ tab: "tombstones" }),
    "3": () => update({ tab: "chain" }),
    "4": () => update({ tab: "redaction" }),
  },
})

const shortcutGroups = [
  {
    title: "This page",
    rows: [
      { keys: "/", label: "Focus the filter box" },
      { keys: "1 / 2 / 3 / 4", label: "Coverage ledger · Tombstones · Evidence chain · Redaction" },
      { keys: "y", label: "Copy link to this view" },
      { keys: "g p", label: "Go to policies" },
      { keys: "g d", label: "Go to drift" },
      { keys: "g a", label: "Go to audit log" },
      { keys: "?", label: "Show this sheet" },
    ],
  },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <EvidenceHeader
      ref="header"
      :range="state.range"
      @update:range="update({ range: $event as EvidenceRange })"
    />

    <section class="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[0.6875rem] text-fg-3" aria-label="Evidence summary">
      <span>
        {{ tombstones.length }} tombstones in range ·
        <span v-if="incompleteTombstones > 0" class="text-warn">{{ incompleteTombstones }} with an open step</span>
        <span v-else class="text-ok">all fully applied</span>
      </span>
      <span>
        Chain:
        <span v-if="openChain > 0" class="text-crit">{{ openChain }} row(s) not settled</span>
        <span v-else class="text-ok">every recorded row settled</span>
      </span>
      <span v-if="newestEvidence">Newest evidence row {{ formatGovernRelative(newestEvidence) }}</span>
      <GovernCopyId :id="EVIDENCE_SUMMARY_CONTRACT" label="Summary contract" truncate />
    </section>

    <GovernTabBar
      :tabs="tabs"
      :model-value="state.tab"
      aria-label="Evidence views"
      :badges="tabBadges"
      @update:model-value="update({ tab: $event as EvidenceTab })"
    />

    <GovernFilterBar
      ref="search"
      :model-value="state.q"
      :label="placeholders[state.tab]"
      :placeholder="placeholders[state.tab]"
      :result-text="
        state.tab === 'ledger'
          ? `${ledgerRows.length} of ${producers.length} producers`
          : state.tab === 'tombstones'
            ? `${tombstoneRows.length} of ${tombstones.length} tombstones`
            : state.tab === 'chain'
              ? `${chainRows.length} of ${chain.length} chain rows`
              : `${redaction.length} of ${EVIDENCE_REDACTION_ROWS.length} pipelines`
      "
      :active="activeFilters > 0"
      @update:model-value="update({ q: $event })"
      @clear="clearFilters"
    >
      <template #filters>
        <GovernFilterSelect
          v-if="state.tab === 'ledger'"
          label="Producer"
          :model-value="state.component"
          :options="componentOptions"
          default-value="all"
          @update:model-value="update({ component: $event })"
        />
        <GovernFilterSelect
          v-if="state.tab === 'tombstones'"
          label="Basis"
          :model-value="state.basis"
          :options="basisOptions"
          default-value="all"
          @update:model-value="update({ basis: $event as DeletionBasis | 'all' })"
        />
        <GovernFilterSelect
          v-if="state.tab === 'chain'"
          label="State"
          :model-value="state.chainState"
          :options="chainStateOptions"
          default-value="all"
          @update:model-value="update({ chainState: $event as ChainState | 'all' })"
        />
      </template>
    </GovernFilterBar>

    <EvidenceLedgerPanel
      v-if="state.tab === 'ledger'"
      :rows="ledgerRows"
      :selected="state.component"
      @select="update({ component: $event })"
    />
    <EvidenceTombstonePanel v-else-if="state.tab === 'tombstones'" :rows="tombstoneRows" />
    <EvidenceChainPanel v-else-if="state.tab === 'chain'" :rows="chainRows" :counts="chainCounts" />
    <EvidenceRedactionPanel v-else :rows="redaction" />

    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
