<script setup lang="ts">
import { computed } from "vue"
import { Download } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import EvidenceCoveragePanel from "./EvidenceCoveragePanel.vue"
import EvidenceDeliveryPanel from "./EvidenceDeliveryPanel.vue"
import EvidenceUnavailablePanel from "./EvidenceUnavailablePanel.vue"
import { useOperatorEvidenceSummary } from "@/composables/useOperatorData"
import { formatGovernNumber, formatGovernRelative } from "@/lib/govern-format"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import {
  EVIDENCE_RANGES,
  EVIDENCE_RANGE_LABELS,
  EVIDENCE_TAB_LABELS,
  serializeLiveEvidenceQuery,
  type EvidenceTab,
  type LiveEvidenceQuery,
} from "~~/shared/operator/evidence-query"
import { deliveryTotal, unsettledDelivery } from "@/lib/evidence-summary"

const props = defineProps<{ state: LiveEvidenceQuery }>()
const emit = defineEmits<{ update: [state: LiveEvidenceQuery] }>()

const summaryState = useOperatorEvidenceSummary(() => serializeLiveEvidenceQuery(props.state))
const summary = computed(() => summaryState.data.value ?? null)
const error = computed(() => summaryState.error.value)
const authIssue = computed(() => isOperatorAuthError(error.value))
const failureDetail = computed(() =>
  error.value && !authIssue.value ? operatorFailureDetail(error.value) : null,
)
const loading = computed(() => !summary.value && !error.value && summaryState.status.value === "pending")

const rangeOptions = EVIDENCE_RANGES.map((range) => ({ value: range, label: EVIDENCE_RANGE_LABELS[range] }))

const tabs = computed(() => [
  { id: "coverage", label: EVIDENCE_TAB_LABELS.coverage },
  { id: "delivery", label: EVIDENCE_TAB_LABELS.delivery },
  { id: "tombstones", label: EVIDENCE_TAB_LABELS.tombstones },
  { id: "redaction", label: EVIDENCE_TAB_LABELS.redaction },
])

const tabBadges = computed<Record<string, string>>(() => {
  const badges: Record<string, string> = {}
  const data = summary.value
  if (!data) return badges
  const unsettled = unsettledDelivery(data.delivery)
  badges.coverage = formatGovernNumber(data.runs_total)
  badges.delivery = unsettled > 0
    ? `${formatGovernNumber(unsettled)} open`
    : formatGovernNumber(deliveryTotal(data.delivery))
  return badges
})

const verdict = computed(() => {
  if (loading.value) return "Reading the evidence summary for this organization…"
  if (authIssue.value) return "The operator session cannot read this organization"
  if (error.value) return "Evidence summary unavailable"
  const data = summary.value
  if (!data) return "Evidence summary unavailable"
  if (data.runs_total === 0) return "No evidence run was recorded in this window"
  const incomplete = data.runs_total - data.capture_complete_runs
  const open = unsettledDelivery(data.delivery)
  if (incomplete === 0 && open === 0) {
    return `${formatGovernNumber(data.runs_total)} runs, every one a complete capture and every event settled`
  }
  return `${formatGovernNumber(data.capture_complete_runs)} of ${formatGovernNumber(data.runs_total)} runs have a complete capture; ${formatGovernNumber(open)} outbox event(s) are unsettled`
})

const coverage = computed(() => {
  const data = summary.value
  if (!data) return "No data shown"
  return `${formatGovernNumber(data.runs_total)} runs · ${formatGovernNumber(deliveryTotal(data.delivery))} outbox events`
})

const observed = computed(() => summary.value?.observed_at ?? null)

const notes = [
  {
    lead: "A completeness value describes the record.",
    body: "Complete means the run's record holds the full capture. Partial, sampled, late, redacted, expired, deleted, and simulated each name why it does not, and the page never folds them into one verdict.",
  },
  {
    lead: "Delivery is a separate axis.",
    body: "The outbox carries no run reference, so relay health is reported for the organization, not per run. A complete capture that has not reached its sink is shown as exactly that.",
  },
  {
    lead: "Tombstones and redaction need their own read models.",
    body: "Those tabs render an explicit unavailable state instead of fixtures. There is no contract behind them yet.",
  },
]

function update(patch: Partial<LiveEvidenceQuery>): void {
  emit("update", { ...props.state, ...patch })
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      title="Evidence"
      definition="Which runs hold a complete capture, which do not, and whether the delivery chain behind them settled."
      state="live"
      :verdict="verdict"
      contract="operator.evidence.summary.v1"
      scope="Organization"
      :range="EVIDENCE_RANGE_LABELS[state.range]"
      :coverage="coverage"
      :observed="observed"
      caveat="Complete capture is a statement about the record. It is not a delivery guarantee, and it is not a population estimate."
      :notes="notes"
    >
      <template #actions>
        <GovernFilterSelect
          label="Range"
          :model-value="state.range"
          :options="rangeOptions"
          default-value="24h"
          @update:model-value="update({ range: $event as LiveEvidenceQuery['range'] })"
        />
        <GovernLockedAction label="Export" :icon="Download" />
      </template>
    </ConsolePageHeader>

    <section class="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[0.6875rem] text-fg-3" aria-label="Evidence summary">
      <span v-if="summary && summary.last_run_at">
        Newest run {{ formatGovernRelative(summary.last_run_at) }}
      </span>
      <GovernCopyId id="operator.evidence.summary.v1" label="Summary contract" truncate />
    </section>

    <GovernTabBar
      :tabs="tabs"
      :model-value="state.tab"
      aria-label="Evidence views"
      :badges="tabBadges"
      @update:model-value="update({ tab: $event as EvidenceTab })"
    />

    <!-- Tabs without a contract explain themselves regardless of the read state;
         they never depend on the summary and never substitute fixtures. -->
    <EvidenceUnavailablePanel
      v-if="state.tab === 'tombstones'"
      title="Tombstone history is not part of this contract"
      reason="operator.evidence.summary.v1 reports capture completeness and relay delivery. Deletion chains, downstream receipts, and hold scope need their own read model, so this tab renders nothing rather than fixtures."
      next-step="Use the memory and session records for a specific subject, or open the privacy governance contract once it exists."
      action-label="Open memories"
      action-to="/memories"
    />
    <EvidenceUnavailablePanel
      v-else-if="state.tab === 'redaction'"
      title="Redaction detail is not part of this contract"
      reason="The summary reports how many runs are redacted, not which fields were removed from each. Field-level redaction evidence needs its own read model."
      next-step="Open a memory record to see its redaction flags, or read the capture policy on this page."
      action-label="Back to coverage"
      action-to="/evidence"
    />
    <IxVerdict
      v-else-if="loading"
      tone="unknown"
      eyebrow="Live operator read"
      title="Reading the evidence summary"
      body="Asking the operator API for the selected window."
    />
    <IxVerdict
      v-else-if="authIssue"
      tone="unavailable"
      eyebrow="Operator session"
      title="The operator session cannot read this organization"
      body="Sign in again with an account that holds metadata-read permission."
    />
    <IxVerdict
      v-else-if="error"
      tone="unknown"
      eyebrow="Live operator read"
      title="Evidence summary unavailable"
      :body="failureDetail ?? 'The upstream read failed. No values are inferred.'"
    />
    <EvidenceDeliveryPanel v-else-if="summary && state.tab === 'delivery'" :summary="summary" />
    <EvidenceCoveragePanel v-else-if="summary" :summary="summary" />
  </div>
</template>
