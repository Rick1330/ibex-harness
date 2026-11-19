<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { RefreshCw, Search, SlidersHorizontal } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import SessionColumnsMenu from "./SessionColumnsMenu.vue"
import SessionFilterPanel from "./SessionFilterPanel.vue"
import SessionTable from "./SessionTable.vue"
import { useOperatorAgents, useOperatorSessions } from "@/composables/useOperatorData"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import {
  DEFAULT_SESSION_COLUMNS,
  DEFAULT_SESSION_PAGE_FILTERS,
  activeSessionFilterCount,
  agentFilterOptions,
  filterSessionRows,
  segmentSessionRows,
  sessionFacets,
  sessionSegments,
  toSessionListRows,
  type SessionColumnId,
  type SessionPageFilters,
  type SessionSegment,
} from "@/lib/session-list"
import { serializeLiveSessionQuery, type LiveSessionQuery } from "~~/shared/operator/session-query"
import type { OperatorSessionRecord, SessionStatus } from "~~/shared/operator/contracts"

const props = defineProps<{ state: LiveSessionQuery; returnTo: string }>()
const emit = defineEmits<{ update: [state: LiveSessionQuery] }>()

/**
 * The agents read is the join source for the Agent column. 100 is the API's
 * page cap, and there is no "agents by id" query, so a session whose agent is
 * outside this page keeps its own id and reports no name.
 */
const AGENT_PAGE_QUERY = new URLSearchParams({ limit: "100" })

const sessionsState = useOperatorSessions(() => serializeLiveSessionQuery(props.state))
const agentsState = useOperatorAgents(() => AGENT_PAGE_QUERY)

const sessions = computed<OperatorSessionRecord[]>(() => sessionsState.data.value?.data ?? [])
const agents = computed(() => agentsState.data.value?.data ?? [])
const pagination = computed(() => sessionsState.data.value?.pagination ?? null)
const error = computed(() => sessionsState.error.value)
const pending = computed(() => sessionsState.status.value === "pending")
const loading = computed(() => pending.value && !sessionsState.data.value && !error.value)
const authIssue = computed(() => isOperatorAuthError(error.value))
const failureDetail = computed(() =>
  error.value && !authIssue.value ? operatorFailureDetail(error.value) : null,
)

const pageFilters = ref<SessionPageFilters>({ ...DEFAULT_SESSION_PAGE_FILTERS })
const segment = ref<SessionSegment["id"]>("all")
const columns = ref<SessionColumnId[]>([...DEFAULT_SESSION_COLUMNS])
const filtersOpen = ref(false)

const rows = computed(() => toSessionListRows(sessions.value, agents.value))
const filteredRows = computed(() => filterSessionRows(rows.value, pageFilters.value))
const segments = computed(() => sessionSegments(filteredRows.value))
const activeSegment = computed<SessionSegment["id"]>(() =>
  segments.value.some((entry) => entry.id === segment.value) ? segment.value : "all",
)

// The tab on screen is the state: a narrowing filter can remove the selected
// segment, and a later read must not resurrect a segment nobody can see.
watch(activeSegment, (value) => {
  segment.value = value
})
const visibleRows = computed(() => segmentSessionRows(filteredRows.value, activeSegment.value))
const segmentTabs = computed(() => segments.value.map((entry) => ({ id: entry.id, label: entry.label })))
const segmentBadges = computed<Record<string, string>>(() =>
  Object.fromEntries(segments.value.map((entry) => [entry.id, String(entry.count)])),
)
const facets = computed(() => ({
  models: sessionFacets(rows.value, "model"),
  providers: sessionFacets(rows.value, "provider"),
}))
const agentOptions = computed(() => agentFilterOptions(agents.value, props.state.agentId))
const filterCount = computed(() =>
  activeSessionFilterCount(pageFilters.value, { status: props.state.status, agentId: props.state.agentId }),
)

const verdict = computed(() => {
  if (loading.value) return "Reading the session index…"
  if (authIssue.value) return "The operator session cannot read this organization"
  if (error.value) return "Session index unavailable"
  return `${visibleRows.value.length} of ${rows.value.length} sessions on this page shown`
})

const coverage = computed(() => {
  if (error.value) return "No data shown"
  if (loading.value) return "Reading live data"
  return `${rows.value.length} rows in one cursor page`
})

const resultText = computed(() => {
  if (loading.value) return "Reading the page…"
  if (error.value) return "No rows shown"
  return `${visibleRows.value.length} of ${rows.value.length} rows on this page`
})

type SessionEmpty = {
  title: string
  reason: string
  nextStep: string | null
  actionLabel: string | null
  action: "clear" | "first" | null
}

function emptyCopy(): SessionEmpty {
  if (rows.value.length > 0) {
    return {
      title: "No sessions match these filters",
      reason: "The rows loaded on this page were narrowed to nothing. The API returned the page before these filters ran.",
      nextStep: "Clear the filters to widen the search.",
      actionLabel: "Clear filters",
      action: "clear",
    }
  }
  if (props.state.cursor) {
    return {
      title: "No sessions on this page",
      reason: "This cursor page is empty, but earlier pages may still hold sessions.",
      nextStep: null,
      actionLabel: "First page",
      action: "first",
    }
  }
  if (props.state.status !== null || props.state.agentId !== null) {
    return {
      title: "No sessions match this filter",
      reason: "The linked read returned no rows for this organization.",
      nextStep: "Remove the filter to read every outcome.",
      actionLabel: "Clear filters",
      action: "clear",
    }
  }
  return {
    title: "No sessions in this organization yet",
    reason: "Sessions appear here once an agent records a turn for this tenant.",
    nextStep: null,
    actionLabel: null,
    action: null,
  }
}

const empty = computed(() => emptyCopy())

function emitQuery(patch: Partial<LiveSessionQuery>): void {
  emit("update", { ...props.state, ...patch, cursor: null })
}

function onAgent(value: string | null): void {
  if (value !== props.state.agentId) emitQuery({ agentId: value })
}

function onStatus(value: SessionStatus | null): void {
  if (value !== props.state.status) emitQuery({ status: value })
}

function onPageFilters(patch: Partial<SessionPageFilters>): void {
  pageFilters.value = { ...pageFilters.value, ...patch }
}

function clearFilters(): void {
  pageFilters.value = { ...DEFAULT_SESSION_PAGE_FILTERS }
  segment.value = "all"
  if (props.state.status !== null || props.state.agentId !== null) emitQuery({ status: null, agentId: null })
}

function runEmptyAction(): void {
  if (empty.value.action === "first") {
    emitQuery({ cursor: null })
    return
  }
  clearFilters()
}

/**
 * Refresh both reads. The agents read is the join behind the Agent column and
 * the agent selector, so a transient failure it hits must be retryable here:
 * refreshing only the sessions read would leave "Agent read unavailable" and an
 * empty selector on screen after the API recovered.
 */
function refresh(): void {
  void Promise.all([sessionsState.refresh(), agentsState.refresh()]).catch(() => undefined)
}

// A page-scoped filter describes the rows that were loaded, so a new read (a
// cursor page, a filter change from the address bar) starts from a clean page.
watch(
  () => props.state,
  () => {
    pageFilters.value = { ...DEFAULT_SESSION_PAGE_FILTERS }
    segment.value = "all"
  },
)
</script>

<template>
  <div class="flex min-w-0 flex-col gap-4">
    <ConsolePageHeader
      title="Sessions"
      state="live"
      :verdict="verdict"
      contract="operator.sessions.v1"
      scope="Organization"
      :range="state.cursor ? 'Cursor page' : 'First page'"
      :coverage="coverage"
      caveat="Message content, hashes, and provider request ids are not part of this contract and are not shown."
    >
      <template #actions>
        <button
          type="button"
          class="ix-button-secondary inline-flex items-center gap-1.5"
          :disabled="pending"
          @click="refresh"
        >
          <RefreshCw :size="13" :stroke-width="2" :class="{ 'animate-spin': pending }" aria-hidden="true" />
          Refresh
        </button>
      </template>
    </ConsolePageHeader>

    <div class="flex flex-wrap items-center gap-2">
      <div class="relative min-w-56 flex-1 sm:max-w-80">
        <Search
          :size="14"
          :stroke-width="2"
          class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3"
          aria-hidden="true"
        />
        <input
          v-model="pageFilters.search"
          type="search"
          class="ix-input w-full pl-8"
          placeholder="Session ID or external ID"
          aria-label="Search sessions"
          autocomplete="off"
        >
      </div>

      <button
        type="button"
        class="ix-button-secondary inline-flex items-center gap-1.5 lg:hidden"
        :aria-expanded="filtersOpen"
        aria-controls="session-filters"
        @click="filtersOpen = !filtersOpen"
      >
        <SlidersHorizontal :size="13" :stroke-width="2" aria-hidden="true" />
        Filters<span v-if="filterCount > 0" class="font-mono text-[0.6875rem] text-accent">{{ filterCount }}</span>
      </button>

      <SessionColumnsMenu v-model="columns" />

      <p class="ml-auto text-[0.6875rem] leading-4 text-fg-3">{{ resultText }}</p>
    </div>

    <IxVerdict
      v-if="authIssue"
      tone="unavailable"
      eyebrow="Live operator read"
      title="An operator session is required to read sessions"
      body="Sign in with a session that can read this organization. No fixture rows are substituted."
      sign-in
    >
      <template #actions>
        <button type="button" class="ix-button-secondary" @click="refresh">Try again</button>
      </template>
    </IxVerdict>

    <IxVerdict
      v-else-if="error"
      tone="unavailable"
      eyebrow="Live operator read"
      title="Session index unavailable"
      :body="failureDetail ?? 'The operator API did not return a verified snapshot.'"
    >
      <template #actions>
        <button type="button" class="ix-button-secondary" @click="refresh">Try again</button>
      </template>
    </IxVerdict>

    <div v-else class="grid min-w-0 gap-4 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start">
      <div :class="filtersOpen ? 'block' : 'hidden lg:block'" class="min-w-0 lg:sticky lg:top-4">
        <SessionFilterPanel
          :scope="{ status: state.status, agentId: state.agentId }"
          :options="{ agents: agentOptions, models: facets.models, providers: facets.providers }"
          :filters="pageFilters"
          @agent="onAgent"
          @status="onStatus"
          @page="onPageFilters"
          @clear="clearFilters"
        />
      </div>

      <div
        id="session-results"
        role="tabpanel"
        :aria-labelledby="`govern-tab-${activeSegment}`"
        class="flex min-w-0 flex-col gap-3"
      >
        <GovernTabBar
          :tabs="segmentTabs"
          :model-value="activeSegment"
          :badges="segmentBadges"
          aria-label="Session status segments"
          panel-id="session-results"
          @update:model-value="segment = $event as SessionSegment['id']"
        />
        <p class="text-[0.6875rem] leading-4 text-fg-3">
          Segment counts cover the rows loaded on this page. The API returns no organization total, so none is claimed.
        </p>

        <GovernEmptyState
          v-if="!loading && visibleRows.length === 0"
          :title="empty.title"
          :reason="empty.reason"
          :next-step="empty.nextStep"
          :action-label="empty.actionLabel"
          @action="runEmptyAction"
        />
        <SessionTable
          v-else
          :rows="visibleRows"
          :loading="loading"
          :columns="columns"
          :return-to="returnTo"
          :agent-read-failed="Boolean(agentsState.error.value)"
        />
      </div>
    </div>

    <nav
      v-if="!error && (sessions.length > 0 || state.cursor)"
      class="flex flex-wrap items-center justify-end gap-2"
      aria-label="Session pages"
    >
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="ix-button-secondary"
          :disabled="!state.cursor || pending"
          @click="emit('update', { ...state, cursor: null })"
        >
          First page
        </button>
        <button
          type="button"
          class="ix-button-secondary"
          :disabled="!pagination?.has_more || !pagination?.next_cursor || pending"
          @click="emit('update', { ...state, cursor: pagination?.next_cursor ?? null })"
        >
          Next page
        </button>
      </div>
    </nav>
  </div>
</template>
