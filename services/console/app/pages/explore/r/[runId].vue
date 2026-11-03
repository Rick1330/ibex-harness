<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, ArrowUpRight, Download } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernIdChip from "@/components/console/govern/primitives/GovernIdChip.vue"
import { useConsoleDemo } from "@/composables/useConsoleDemo"
import { demoTraceDetail } from "@/lib/console-demo"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import IxTierMark from "@/components/console/IxTierMark.vue"
import ExploreRunAssemblyPanel from "@/components/console/explore/run/ExploreRunAssemblyPanel.vue"
import ExploreRunEvidencePanel from "@/components/console/explore/run/ExploreRunEvidencePanel.vue"
import ExploreRunOverviewPanel from "@/components/console/explore/run/ExploreRunOverviewPanel.vue"
import ExploreRunRawPanel from "@/components/console/explore/run/ExploreRunRawPanel.vue"
import ExploreRunTimeline from "@/components/console/explore/run/ExploreRunTimeline.vue"
import ExploreRunToolsPanel from "@/components/console/explore/run/ExploreRunToolsPanel.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { formatGovernStampMillis } from "@/lib/govern-format"
import { tierForTrace } from "@/lib/certification"
import { safeExploreReturn } from "@/lib/return-to"
import {
  EXPLORE_RUN_TABS,
  EXPLORE_RUN_TAB_LABELS,
  EXPLORE_RUN_TAB_MEANING,
  exploreRunHref,
  parseExploreRunQuery,
  type ExploreRunState,
  type ExploreRunTab,
} from "@/lib/govern-query"
import {
  COMPLETENESS_LABELS,
  EXPLORE_RUN_NOTES,
  EXPLORE_TRACE_DETAIL_CONTRACT,
  PUBLICATION_LABELS,
  TRACE_STATUS_LABELS,
  completenessClass,
  publicationClass,
} from "@/lib/explore-view"

const route = useRoute()
const runId = computed(() => String(route.params.runId ?? ""))
const returnTo = computed(() => safeExploreReturn(route.query.return))

// Keyed on the id alone: a new run must re-read rather than re-label the previous payload,
// while a tab or lens change only rewrites the query.
definePageMeta({ key: (pageRoute) => String(pageRoute.params.runId ?? "") })

const detailState = useTraceDetail(runId.value)
const demo = useConsoleDemo()
const demoActive = computed(() => demo.value && !detailState.data.value && Boolean(demoTraceDetail(runId.value)))
const detail = computed(() => detailState.data.value ?? (demoActive.value ? demoTraceDetail(runId.value) : null))

const state = ref<ExploreRunState>(parseExploreRunQuery(route.query))

watch(
  () => route.query,
  () => {
    if (!route.path.startsWith("/explore/r/")) return
    state.value = parseExploreRunQuery(route.query)
  },
)

function update(next: ExploreRunState): void {
  state.value = next
  if (!import.meta.client) return
  void navigateTo(exploreRunHref(runId.value, next, returnTo.value), { replace: true })
}

function goTab(tab: ExploreRunTab): void {
  update({ ...state.value, tab })
}

useHead(() => ({
  title: `${detail.value?.run_id ?? runId.value} · Run detail · IBEX Console`,
}))

const errorStatus = computed(() => {
  const status = (detailState.error.value as { statusCode?: number } | null)?.statusCode
  return status ?? null
})
const authIssue = computed(() => !demoActive.value && (errorStatus.value === 401 || errorStatus.value === 403))
const notFound = computed(() => errorStatus.value === 404)
const reading = computed(() => detail.value === null && !detailState.error.value)

const headerState = computed<"live" | "partial" | "illustrative">(() => (demoActive.value ? "illustrative" : detail.value ? "live" : "partial"))
const tier = computed(() => (detail.value ? tierForTrace(detail.value) : null))

const tabs = EXPLORE_RUN_TABS.map((id) => ({ id, label: EXPLORE_RUN_TAB_LABELS[id] }))

const badges = computed<Record<string, string>>(() => {
  const value = detail.value
  if (!value) return {}
  const counts: Record<string, string> = {}
  if (value.spans.length) counts.timeline = String(value.spans.length)
  if (value.candidates.length) counts.assembly = String(value.candidates.length)
  if (value.tools.length) counts.tools = String(value.tools.length)
  return counts
})

const statusLine = computed(() => {
  if (authIssue.value) {
    return {
      tone: "warning" as const,
      text: "Operator session required. Run evidence is read with your session and nothing is substituted for it.",
    }
  }
  if (detailState.error.value && !demoActive.value) {
    return {
      tone: "warning" as const,
      text: "Run evidence unavailable. The run may not exist in this organization, may have expired under retention, or the upstream read failed.",
    }
  }
  const value = detail.value
  if (!value) return { tone: "muted" as const, text: "Reading run evidence for your organization." }
  const missing = value.unavailable_sections.length
  const parts = [
    TRACE_STATUS_LABELS[value.status],
    `${COMPLETENESS_LABELS[value.evidence.completeness].toLowerCase()} record`,
    PUBLICATION_LABELS[value.evidence.publication_state].toLowerCase(),
  ]
  return {
    tone: value.status === "error" ? ("warning" as const) : ("ok" as const),
    text: `${parts.join(" · ")}${value.error_code ? ` · ${value.error_code}` : ""}. ${
      missing
        ? `${missing} section${missing === 1 ? " is" : "s are"} explicitly unrecorded.`
        : "No section is marked unrecorded."
    }`,
  }
})


const verdictTone = computed(() => {
  if (statusLine.value.tone === "ok") return "healthy" as const
  if (statusLine.value.tone === "warning") return "attention" as const
  return "unknown" as const
})
function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(
    `${window.location.origin}${exploreRunHref(runId.value, state.value, returnTo.value)}`,
  )
}

const { helpOpen } = useGovernShortcuts({
  onEscape: () => goTab("overview"),
  keys: {
    y: copyCurrentLink,
    "1": () => goTab("overview"),
    "2": () => goTab("timeline"),
    "3": () => goTab("evidence"),
    "4": () => goTab("assembly"),
    "5": () => goTab("tools"),
    "6": () => goTab("raw"),
  },
})

const shortcutGroups = [
  {
    title: "This page",
    rows: [
      { keys: "1 – 6", label: "Switch section" },
      { keys: "y", label: "Copy a link to this section and lens" },
      { keys: "Esc", label: "Return to the overview section" },
      { keys: "g x", label: "Go to Explore" },
      { keys: "?", label: "Show this sheet" },
    ],
  },
]

const traceHref = computed<string | null>(() =>
  detail.value
    ? `/explore/t/${encodeURIComponent(detail.value.trace_id)}?return=${encodeURIComponent(returnTo.value)}`
    : null,
)

function backToList(): void {
  void navigateTo(returnTo.value)
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      :title="`Run ${runId.length > 14 ? `${runId.slice(0, 12)}…` : runId}`"
      definition="Everything the detail contract returned for this run — and the sections it explicitly did not."
      :state="headerState"
      :observed="detail?.evidence.observed_at ?? null"
      :scope="demoActive ? `ibex-demo · illustrative run ${runId}` : `Current organization · run ${runId}`"
      :contract="EXPLORE_TRACE_DETAIL_CONTRACT"
      :verdict="
        demoActive
          ? 'Illustrative development data. The operator API is not connected in this environment, so this run detail is a recorded fixture. It is not a live evidence read and makes no production claim.'
          : detail
            ? 'This is the validated detail payload for one run, read with your operator session. Sections the contract did not supply are named as unrecorded rather than filled in.'
            : 'The detail read did not resolve. Nothing here is reconstructed from the list row that linked to it.'
      "
      :range="detail ? `Evidence observed ${formatGovernStampMillis(detail.evidence.observed_at)}` : 'Run identifier supplied by the caller'"
      :notes="EXPLORE_RUN_NOTES"
    >
      <template #back>
        <NuxtLink
          :to="returnTo"
          class="inline-flex items-center gap-1 text-xs text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          <ArrowLeft :size="12" :stroke-width="1.9" aria-hidden="true" />
          Explore
        </NuxtLink>
      </template>

      <template #eyebrow>
        <div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          <span class="font-mono text-[0.6875rem] leading-4 text-fg-3">Investigate · Run detail</span>
          <GovernIdChip :value="runId" label="Run ID" />
        </div>
      </template>

      <template #actions>
        <NuxtLink v-if="traceHref" :to="traceHref" class="ix-button-secondary h-8 gap-1 text-xs">
          Trace runs
          <ArrowUpRight :size="13" :stroke-width="1.8" aria-hidden="true" />
        </NuxtLink>
        <GovernLockedAction label="Export run record" :icon="Download" />
      </template>

      <div v-if="detail" class="flex flex-wrap items-center gap-1.5">
        <span
          v-if="tier"
          class="inline-flex items-center gap-1.5 rounded-full border border-line-subtle bg-surface px-2 py-0.5 text-[0.6875rem] text-fg-2"
          :title="tier.meaning"
        >
          <IxTierMark :tier="tier.tier" :detail="tier.detail" :record-id="detail.run_id" />
          {{ tier.label }}
        </span>
        <span
          class="inline-flex items-center rounded-full border border-line-subtle bg-surface px-2 py-0.5 font-mono text-[0.6875rem] leading-4"
          :class="completenessClass(detail.evidence.completeness)"
        >
          {{ COMPLETENESS_LABELS[detail.evidence.completeness] }}
        </span>
        <span
          class="inline-flex items-center rounded-full border border-line-subtle bg-surface px-2 py-0.5 font-mono text-[0.6875rem] leading-4"
          :class="publicationClass(detail.evidence.publication_state)"
        >
          {{ PUBLICATION_LABELS[detail.evidence.publication_state] }}
        </span>
      </div>
    </ConsolePageHeader>

    <IxVerdict
      :tone="verdictTone"
      eyebrow="Current read"
      :title="statusLine.text"
      :meta="detail?.evidence.observed_at ? formatGovernStampMillis(detail.evidence.observed_at) : undefined"
    />

    <template v-if="detail">
      <GovernTabBar
        :tabs="tabs"
        :model-value="state.tab"
        :badges="badges"
        aria-label="Run sections"
        @update:model-value="goTab($event as ExploreRunTab)"
      />
      <p class="-mt-1 text-[0.6875rem] leading-4 text-fg-3">{{ EXPLORE_RUN_TAB_MEANING[state.tab] }}</p>

      <ExploreRunOverviewPanel v-if="state.tab === 'overview'" :detail="detail" />
      <ExploreRunTimeline
        v-else-if="state.tab === 'timeline'"
        :detail="detail"
        :lens="state.lens"
        @update:lens="update({ ...state, lens: $event })"
      />
      <ExploreRunEvidencePanel v-else-if="state.tab === 'evidence'" :detail="detail" />
      <ExploreRunAssemblyPanel v-else-if="state.tab === 'assembly'" :detail="detail" />
      <ExploreRunToolsPanel v-else-if="state.tab === 'tools'" :detail="detail" />
      <ExploreRunRawPanel v-else :detail="detail" />

      <GovernCaveat tone="lock" title="What this page does not prove">
        It proves one run was observed with the metadata shown, and that its evidence row is in the state reported. It does
        not prove the prompt content, that the run was billed, or that a deletion reached every store — each of those lives
        behind its own contract.
      </GovernCaveat>
    </template>

    <div v-else-if="reading" class="min-w-0 rounded-lg border border-line-subtle bg-surface-1 px-4 py-10 text-center">
      <p class="text-sm font-medium text-fg-1">Reading run evidence</p>
      <p class="mt-1 text-xs leading-4 text-fg-3">
        The layout is held while the tenant-scoped detail resolves. Nothing is drawn from the list row that linked here.
      </p>
    </div>

    <GovernEmptyState
      v-else-if="notFound"
      :title="`No run record for ${runId.length > 20 ? `${runId.slice(0, 20)}…` : runId}`"
      reason="The identifier resolved to nothing inside your organization. Run evidence is never reconstructed from an identifier, and another organization's run is reported the same way."
      next-step="Check the run id against the query that produced it, or open the trace to see the runs that do exist."
      action-label="Back to Explore"
      @action="backToList"
    />

    <GovernEmptyState
      v-else-if="authIssue"
      title="Operator session required"
      reason="The access cookie is missing, expired, or lacks run-detail permission. No preview record is substituted for a refused read."
      next-step="Sign in with an operator account that holds metadata-read permission."
    />

    <GovernEmptyState
      v-else
      title="Run evidence unavailable"
      reason="The upstream read failed. The console reports the failure rather than rendering a partial record without saying so."
      next-step="Reload to retry; if it persists, the run may have expired under retention."
    />

    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
