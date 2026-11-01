<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { RefreshCw } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import CompositionBar from "@/components/console/CompositionBar.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import PlatformDependencyPanel from "./PlatformDependencyPanel.vue"
import PlatformPipelinePanel from "./PlatformPipelinePanel.vue"
import PlatformRawPanel from "./PlatformRawPanel.vue"
import PlatformRecoveryPanel from "./PlatformRecoveryPanel.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { useConsoleDemo } from "@/composables/useConsoleDemo"
import { formatGovernStamp } from "@/lib/govern-format"
import { DEMO_CONTEXT, DEMO_PLATFORM_HEALTH } from "@/lib/console-demo"
import {
  PLATFORM_TAB_LABELS,
  PLATFORM_TAB_MEANING,
  platformHref,
  type PlatformState,
  type PlatformTab,
} from "@/lib/govern-query"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import { platformDependencyCounts, platformDependencyEntries, platformReadinessState } from "@/lib/platform-readiness"
import {
  PLATFORM_CONTRACT,
  PLATFORM_NOTES,
  platformDependencyRows,
  platformDigest,
  platformPipelineFields,
  platformRecoveryFields,
  platformStaleness,
  platformTiles,
  platformVerdict,
} from "@/lib/platform-view"

const props = defineProps<{ state: PlatformState }>()
const emit = defineEmits<{ update: [state: PlatformState] }>()

const healthState = usePlatformHealth()
const contextState = useOperatorContext()
const demo = useConsoleDemo()
const health = computed(() => healthState.data.value ?? (demo.value ? DEMO_PLATFORM_HEALTH : null))
const context = computed(() => contextState.data.value ?? (demo.value ? DEMO_CONTEXT : null))
const demoActive = computed(() => demo.value && !healthState.data.value)

const refreshing = ref(false)
const nowMs = ref<number | null>(null)
let clock: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  nowMs.value = Date.now()
  clock = setInterval(() => {
    nowMs.value = Date.now()
  }, 10_000)
})
onBeforeUnmount(() => {
  if (clock) clearInterval(clock)
})

const authIssue = computed(() => !demoActive.value && isOperatorAuthError(healthState.error.value))
const loading = computed(() => !health.value && !demoActive.value && !healthState.error.value && healthState.status.value === "pending")
const failureDetail = computed(() =>
  !demoActive.value && healthState.error.value && !authIssue.value ? operatorFailureDetail(healthState.error.value) : null,
)

const readiness = computed(() =>
  platformReadinessState({ health: health.value, authIssue: authIssue.value, loading: loading.value }),
)
const staleness = computed(() => platformStaleness(health.value?.observed_at ?? null, nowMs.value))
const counts = computed(() => platformDependencyCounts(platformDependencyEntries(health.value)))

const dependencySegments = computed(() => [
  { label: "Ok", value: counts.value.ok, color: "bg-s1" },
  { label: "Degraded", value: counts.value.degraded, color: "bg-warn" },
  { label: "Unavailable", value: counts.value.unavailable, color: "bg-crit" },
])
const rows = computed(() => platformDependencyRows(health.value))
const verdict = computed(() =>
  platformVerdict({
    health: health.value,
    readiness: readiness.value,
    staleness: staleness.value,
    failureDetail: failureDetail.value,
  }),
)

const verdictTone = computed(() => {
  if (verdict.value.tone === "ok") return "healthy" as const
  if (verdict.value.tone === "warning") return "attention" as const
  return "unknown" as const
})
const tiles = computed(() => platformTiles({ health: health.value, staleness: staleness.value }))
const pipelineFields = computed(() => platformPipelineFields(health.value))
const recoveryFields = computed(() => platformRecoveryFields(health.value, nowMs.value))
const digest = computed(() => platformDigest(health.value))

const tabs = [
  { id: "dependencies", label: PLATFORM_TAB_LABELS.dependencies },
  { id: "pipeline", label: PLATFORM_TAB_LABELS.pipeline },
  { id: "recovery", label: PLATFORM_TAB_LABELS.recovery },
  { id: "raw", label: PLATFORM_TAB_LABELS.raw },
]

function reported(fields: { value: string }[]): string {
  const present = fields.filter((field) => !["Not reported", "Not recorded"].includes(field.value)).length
  return `${present}/${fields.length}`
}

const badges = computed<Record<string, string>>(() => ({
  dependencies: String(counts.value.total),
  pipeline: reported(pipelineFields.value),
  recovery: reported([...recoveryFields.value, { value: digest.value.value ?? "Not recorded" }]),
}))

const headerState = computed<"live" | "partial" | "illustrative">(() => (demoActive.value ? "illustrative" : health.value ? "live" : "partial"))
const scopeText = computed(() => {
  const slug = context.value?.org_slug ?? null
  if (demoActive.value) return slug ? `Platform-wide · ${slug} illustrative development read` : "Platform-wide · illustrative development read"
  return slug
    ? `Platform-wide · read with the ${slug} operator session`
    : "Platform-wide · read with the operator session"
})

const headerVerdict = computed(() => {
  if (demoActive.value) {
    return "Illustrative development data. The operator API is not connected in this environment, so this page is showing a recorded platform snapshot fixture. It is not a live health read and makes no production claim."
  }
  const boundary =
    "One snapshot of one contract, read when this page was opened. It is not a history, an incident record, or a service objective."
  return health.value
    ? `${verdict.value.text} ${boundary}`
    : `${verdict.value.text} ${failureDetail.value ?? "The health read did not resolve."} Nothing is inferred to fill the gap.`
})

function update(patch: Partial<PlatformState>): void {
  emit("update", { ...props.state, ...patch })
}

async function refreshHealth(): Promise<void> {
  refreshing.value = true
  try {
    await Promise.allSettled([healthState.refresh(), contextState.refresh()])
    nowMs.value = Date.now()
  } finally {
    refreshing.value = false
  }
}

function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(`${window.location.origin}${platformHref(props.state)}`)
}

const { helpOpen } = useGovernShortcuts({
  keys: {
    r: refreshHealth,
    y: copyCurrentLink,
    "1": () => update({ tab: "dependencies" }),
    "2": () => update({ tab: "pipeline" }),
    "3": () => update({ tab: "recovery" }),
    "4": () => update({ tab: "raw" }),
  },
})

const shortcutGroups = [
  {
    title: "This page",
    rows: [
      { keys: "1 / 2 / 3 / 4", label: "Ledger · Ingestion · Recovery · Payload" },
      { keys: "r", label: "Re-read the platform snapshot" },
      { keys: "y", label: "Copy link to this tab" },
      { keys: "g x", label: "Go to Explore" },
      { keys: "g e", label: "Go to Evidence" },
      { keys: "?", label: "Show this sheet" },
    ],
  },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      title="Platform"
      definition="The one snapshot the platform publishes about itself: which dependency checks it ran, what it says it is serving in, and which recovery and deployment facts it recorded."
      :state="headerState"
      :observed="health?.observed_at ? formatGovernStamp(health.observed_at) : undefined"
      :scope="scopeText"
      :contract="PLATFORM_CONTRACT"
      :verdict="headerVerdict"
      :range="
        health
          ? `Single snapshot observed ${formatGovernStamp(health.observed_at)} · stale after 5 minutes`
          : 'Single snapshot · none observed on this visit'
      "
      coverage="1 live contract read · no history, incident, or SLO contract connected"
      :notes="PLATFORM_NOTES"
    >
      <template #actions>
        <span class="sr-only" aria-live="polite">{{ refreshing ? "Re-reading the platform snapshot" : "" }}</span>
        <button type="button" class="ix-button-secondary" :disabled="refreshing" @click="refreshHealth">
          <RefreshCw :size="14" :stroke-width="1.75" :class="refreshing && 'animate-spin'" aria-hidden="true" />
          Re-read
        </button>
      </template>
      <p class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.6875rem] leading-4 text-fg-3">
        <span>Checks <span class="font-mono text-fg-2">{{ counts.total }}</span></span>
        <span aria-hidden="true">·</span>
        <span>Findings <span :class="counts.degraded + counts.unavailable > 0 ? 'text-warn' : 'text-fg-2'" class="font-mono">{{ counts.degraded + counts.unavailable }}</span></span>
        <span aria-hidden="true">·</span>
        <span>Mode <span :class="health?.degraded_mode ? 'text-warn' : 'text-fg-2'">{{ health ? (health.degraded_mode ? "Degraded" : "Normal") : "Not reported" }}</span></span>
      </p>
    </ConsolePageHeader>

    <IxVerdict
      :tone="verdictTone"
      eyebrow="Current snapshot"
      :title="verdict.text"
      :body="verdict.caveat ?? undefined"
      :meta="health?.observed_at ? formatGovernStamp(health.observed_at) : undefined"
    />

    <div class="console-panel p-3">
      <CompositionBar title="Dependency state" :segments="dependencySegments" height="md" />
    </div>

    <section class="grid grid-cols-2 gap-2 xl:grid-cols-4" aria-label="Snapshot summary">
      <GovernStatTile
        v-for="tile in tiles"
        :key="tile.label"
        :label="tile.label"
        :value="tile.value"
        :helper="tile.helper"
        :tone="tile.tone"
        compact
      />
    </section>

    <GovernTabBar
      :tabs="tabs"
      :model-value="state.tab"
      :badges="badges"
      aria-label="Platform sections"
      @update:model-value="update({ tab: $event as PlatformTab })"
    />

    <p class="-mt-1 max-w-3xl text-[0.6875rem] leading-4 text-fg-3">{{ PLATFORM_TAB_MEANING[state.tab] }}</p>

    <PlatformDependencyPanel
      v-if="state.tab === 'dependencies'"
      :rows="rows"
      :resolved="Boolean(health)"
      :loading="loading"
      :auth-issue="authIssue"
      @retry="refreshHealth"
    />
    <PlatformPipelinePanel
      v-else-if="state.tab === 'pipeline'"
      :fields="pipelineFields"
      :resolved="Boolean(health)"
    />
    <PlatformRecoveryPanel
      v-else-if="state.tab === 'recovery'"
      :fields="recoveryFields"
      :digest="digest"
      :resolved="Boolean(health)"
    />
    <PlatformRawPanel v-else :health="health" @retry="refreshHealth" />

    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
