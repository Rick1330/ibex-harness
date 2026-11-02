<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { RefreshCw, X } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import LiveSessionStatusPill from "./LiveSessionStatusPill.vue"
import { useOperatorSessions } from "@/composables/useOperatorData"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import {
  serializeLiveSessionQuery,
  type LiveSessionQuery,
} from "~~/shared/operator/session-query"
import type { OperatorSessionRecord, SessionStatus } from "~~/shared/operator/contracts"

const props = defineProps<{ state: LiveSessionQuery; returnTo: string }>()
const emit = defineEmits<{ update: [state: LiveSessionQuery] }>()

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const sessionsState = useOperatorSessions(() => serializeLiveSessionQuery(props.state))
const sessions = computed<OperatorSessionRecord[]>(() => sessionsState.data.value?.data ?? [])
const pagination = computed(() => sessionsState.data.value?.pagination ?? null)
const error = computed(() => sessionsState.error.value)
const pending = computed(() => sessionsState.status.value === "pending")
const loading = computed(() => pending.value && !sessionsState.data.value && !error.value)
const authIssue = computed(() => isOperatorAuthError(error.value))
const failureDetail = computed(() =>
  error.value && !authIssue.value ? operatorFailureDetail(error.value) : null,
)

const hasFilters = computed(() => Boolean(props.state.agentId || props.state.status))
const verdict = computed(() => {
  if (loading.value) return "Reading the session index…"
  if (authIssue.value) return "The operator session cannot read this organization"
  if (error.value) return "Session index unavailable"
  if (sessions.value.length === 0) {
    return hasFilters.value ? "No sessions match these filters" : "No sessions in this organization yet"
  }
  return `${sessions.value.length} sessions on this page`
})
const coverage = computed(() => {
  if (error.value) return "No data shown"
  if (loading.value) return "Reading live data"
  return `${sessions.value.length} live rows`
})

const agentDraft = ref(props.state.agentId ?? "")
const agentError = ref("")

watch(
  () => props.state.agentId,
  (value) => {
    if ((value ?? "") !== agentDraft.value) agentDraft.value = value ?? ""
  },
)

function emitFilter(patch: Partial<LiveSessionQuery>): void {
  emit("update", { ...props.state, ...patch, cursor: null })
}

function applyAgent(): void {
  const value = agentDraft.value.trim().toLowerCase()
  if (!value) {
    agentError.value = ""
    if (props.state.agentId) emitFilter({ agentId: null })
    return
  }
  if (!UUID_RE.test(value)) {
    agentError.value = "Enter a full agent UUID"
    return
  }
  agentError.value = ""
  if (value !== props.state.agentId) emitFilter({ agentId: value })
}

function onStatusChange(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  emitFilter({ status: value ? (value as SessionStatus) : null })
}

function clearFilters(): void {
  agentDraft.value = ""
  agentError.value = ""
  emit("update", { ...props.state, agentId: null, status: null, cursor: null })
}

function sessionHref(session: OperatorSessionRecord): string {
  return `/sessions/${encodeURIComponent(session.id)}?return=${encodeURIComponent(props.returnTo)}`
}

function refresh(): void {
  void sessionsState.refresh()
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-5">
    <ConsolePageHeader
      title="Sessions"
      definition="The tenant-scoped session index: status, turn counts, token totals, latency, and extraction progress."
      state="live"
      :verdict="verdict"
      contract="operator.sessions.v1"
      scope="Organization"
      :range="state.cursor ? 'Cursor page' : 'First page'"
      :coverage="coverage"
      caveat="Message content, hashes, and provider request ids are not part of this contract and are not shown."
    >
      <template #actions>
        <button type="button" class="ix-button-secondary inline-flex items-center gap-1.5" :disabled="pending" @click="refresh">
          <RefreshCw :size="13" :stroke-width="2" :class="{ 'animate-spin': pending }" aria-hidden="true" />
          Refresh
        </button>
      </template>
    </ConsolePageHeader>

    <form class="flex flex-wrap items-start gap-2" role="search" @submit.prevent>
      <label class="flex w-72 flex-col gap-1">
        <span class="ix-label">Agent ID</span>
        <input
          v-model="agentDraft"
          type="text"
          class="ix-input w-full font-mono text-xs"
          placeholder="00000000-0000-4000-8000-000000000000"
          autocomplete="off"
          :aria-invalid="Boolean(agentError)"
          @keyup.enter="applyAgent"
          @blur="applyAgent"
        >
        <span v-if="agentError" class="text-[0.6875rem] text-crit">{{ agentError }}</span>
      </label>
      <label class="flex w-40 flex-col gap-1">
        <span class="ix-label">Status</span>
        <select class="ix-input" :value="state.status ?? ''" @change="onStatusChange">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="completed">Completed</option>
          <option value="abandoned">Abandoned</option>
          <option value="error">Error</option>
        </select>
      </label>
      <button v-if="hasFilters" type="button" class="ix-button-secondary mt-5 inline-flex items-center gap-1.5" @click="clearFilters">
        <X :size="13" :stroke-width="2" aria-hidden="true" />
        Clear
      </button>
    </form>

    <IxVerdict
      v-if="authIssue"
      tone="unavailable"
      eyebrow="Live operator read"
      title="An operator session is required to read sessions"
      body="Sign in with a session that can read this organization. No fixture rows are substituted."
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

    <IxVerdict
      v-else-if="!loading && sessions.length === 0"
      tone="unknown"
      eyebrow="Live operator read"
      :title="hasFilters ? 'No sessions match these filters' : 'No sessions in this organization yet'"
      :body="
        hasFilters
          ? 'Clear or change the filters to widen the search. The API returned no rows for this query.'
          : 'Sessions appear here once an agent completes a turn for this tenant.'
      "
    >
      <template #actions>
        <button v-if="state.cursor" type="button" class="ix-button-secondary" @click="emit('update', { ...state, cursor: null })">
          First page
        </button>
        <button v-if="hasFilters" type="button" class="ix-button-secondary" @click="clearFilters">Clear filters</button>
      </template>
    </IxVerdict>

    <div v-else class="overflow-x-auto rounded-lg border border-line-subtle bg-surface">
      <table class="ix-agent-table" aria-label="Sessions">
        <caption class="sr-only">Metadata-only session index for this organization.</caption>
        <thead>
          <tr>
            <th scope="col" class="!pl-4">Session</th>
            <th scope="col" class="w-28">Status</th>
            <th scope="col" class="w-20 text-right">Turns</th>
            <th scope="col" class="hidden w-28 text-right min-[1000px]:table-cell">Tokens</th>
            <th scope="col" class="hidden w-24 text-right min-[1000px]:table-cell">Latency</th>
            <th scope="col" class="hidden w-24 text-right min-[1100px]:table-cell">Extracted</th>
            <th scope="col" class="w-36">Created</th>
          </tr>
        </thead>
        <tbody>
          <template v-if="loading">
            <tr v-for="index in 5" :key="`skeleton-${index}`" aria-hidden="true">
              <td class="!pl-4"><span class="block h-3 w-48 animate-pulse rounded bg-raised" /></td>
              <td><span class="block h-3 w-16 animate-pulse rounded bg-raised" /></td>
              <td><span class="ml-auto block h-3 w-8 animate-pulse rounded bg-raised" /></td>
              <td class="hidden min-[1000px]:table-cell"><span class="ml-auto block h-3 w-16 animate-pulse rounded bg-raised" /></td>
              <td class="hidden min-[1000px]:table-cell"><span class="ml-auto block h-3 w-10 animate-pulse rounded bg-raised" /></td>
              <td class="hidden min-[1100px]:table-cell"><span class="ml-auto block h-3 w-10 animate-pulse rounded bg-raised" /></td>
              <td><span class="block h-3 w-20 animate-pulse rounded bg-raised" /></td>
            </tr>
          </template>
          <template v-else>
            <tr v-for="session in sessions" :key="session.id" :data-session-row="session.id">
              <td class="!pl-4">
                <NuxtLink
                  :to="sessionHref(session)"
                  class="block font-mono text-xs font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                >
                  {{ session.id.slice(0, 8) }}…{{ session.id.slice(-4) }}
                </NuxtLink>
                <span class="mt-0.5 block truncate font-mono text-[0.625rem] leading-4 text-fg-3">
                  agent {{ session.agent_id.slice(0, 8) }} · {{ session.model }}
                </span>
              </td>
              <td><LiveSessionStatusPill :status="session.status" /></td>
              <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ formatGovernNumber(session.turn_count) }}</td>
              <td class="hidden text-right font-mono text-xs text-fg-1 tabular-nums min-[1000px]:table-cell">
                {{ formatGovernNumber(session.total_input_tokens) }} / {{ formatGovernNumber(session.total_output_tokens) }}
              </td>
              <td class="hidden text-right font-mono text-xs text-fg-1 tabular-nums min-[1000px]:table-cell">
                {{ formatGovernNumber(session.total_latency_ms) }} ms
              </td>
              <td class="hidden text-right font-mono text-xs text-fg-1 tabular-nums min-[1100px]:table-cell">
                {{ formatGovernNumber(session.last_extracted_turn) }} / {{ formatGovernNumber(session.turn_count) }}
              </td>
              <td class="text-xs whitespace-nowrap text-fg-2">{{ formatGovernStamp(session.created_at) }}</td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <nav v-if="!error && (sessions.length > 0 || state.cursor)" class="flex flex-wrap items-center justify-between gap-2" aria-label="Session pages">
      <p class="text-xs text-fg-3">Showing {{ sessions.length }} session{{ sessions.length === 1 ? "" : "s" }} from the operator API.</p>
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
