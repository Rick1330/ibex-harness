<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { RefreshCw, X } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import MemoryStatusPill from "./LiveMemoryStatusPill.vue"
import { useOperatorMemories } from "@/composables/useOperatorData"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import {
  serializeLiveMemoryQuery,
  type LiveMemoryQuery,
} from "~~/shared/operator/memory-query"
import type { MemoryCategory, MemoryStatus, OperatorMemory } from "~~/shared/operator/contracts"

const props = defineProps<{ state: LiveMemoryQuery; returnTo: string }>()
const emit = defineEmits<{ update: [state: LiveMemoryQuery] }>()

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const memoriesState = useOperatorMemories(() => serializeLiveMemoryQuery(props.state))
const memories = computed<OperatorMemory[]>(() => memoriesState.data.value?.data ?? [])
const pagination = computed(() => memoriesState.data.value?.pagination ?? null)
const error = computed(() => memoriesState.error.value)
const pending = computed(() => memoriesState.status.value === "pending")
const loading = computed(() => pending.value && !memoriesState.data.value && !error.value)
const authIssue = computed(() => isOperatorAuthError(error.value))
const failureDetail = computed(() =>
  error.value && !authIssue.value ? operatorFailureDetail(error.value) : null,
)

const hasFilters = computed(() =>
  Boolean(props.state.agentId || props.state.sessionId || props.state.status || props.state.category),
)
const verdict = computed(() => {
  if (loading.value) return "Reading the memory index…"
  if (authIssue.value) return "The operator session cannot read this organization"
  if (error.value) return "Memory index unavailable"
  if (memories.value.length === 0) {
    return hasFilters.value ? "No memories match these filters" : "No memories in this organization yet"
  }
  return `${memories.value.length} memories on this page`
})
const coverage = computed(() => {
  if (error.value) return "No data shown"
  if (loading.value) return "Reading live data"
  return `${memories.value.length} live rows`
})

const agentDraft = ref(props.state.agentId ?? "")
const sessionDraft = ref(props.state.sessionId ?? "")
const agentError = ref("")
const sessionError = ref("")

watch(
  () => props.state.agentId,
  (value) => {
    if ((value ?? "") !== agentDraft.value) agentDraft.value = value ?? ""
  },
)
watch(
  () => props.state.sessionId,
  (value) => {
    if ((value ?? "") !== sessionDraft.value) sessionDraft.value = value ?? ""
  },
)

function emitFilter(patch: Partial<LiveMemoryQuery>): void {
  emit("update", { ...props.state, ...patch, cursor: null })
}

function applyUuid(
  draft: string,
  label: "agent" | "session",
): string | null | undefined {
  const value = draft.trim().toLowerCase()
  const setError = label === "agent" ? agentError : sessionError
  if (!value) {
    setError.value = ""
    return null
  }
  if (!UUID_RE.test(value)) {
    setError.value = `Enter a full ${label} UUID`
    return undefined
  }
  setError.value = ""
  return value
}

function applyAgent(): void {
  const value = applyUuid(agentDraft.value, "agent")
  if (value !== undefined && value !== props.state.agentId) emitFilter({ agentId: value })
}

function applySession(): void {
  const value = applyUuid(sessionDraft.value, "session")
  if (value !== undefined && value !== props.state.sessionId) emitFilter({ sessionId: value })
}

function onStatusChange(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  emitFilter({ status: value ? (value as MemoryStatus) : null })
}

function onCategoryChange(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  emitFilter({ category: value ? (value as MemoryCategory) : null })
}

function clearFilters(): void {
  agentDraft.value = ""
  sessionDraft.value = ""
  agentError.value = ""
  sessionError.value = ""
  emit("update", { ...props.state, agentId: null, sessionId: null, status: null, category: null, cursor: null })
}

function memoryHref(memory: OperatorMemory): string {
  return `/memories/${encodeURIComponent(memory.id)}?return=${encodeURIComponent(props.returnTo)}`
}

function refresh(): void {
  void memoriesState.refresh()
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-5">
    <ConsolePageHeader
      title="Memories"
      definition="The tenant-scoped memory index: classification, lifecycle, provenance, usage counters, and validity."
      state="live"
      :verdict="verdict"
      contract="operator.memories.v1"
      scope="Organization"
      :range="state.cursor ? 'Cursor page' : 'First page'"
      :coverage="coverage"
      caveat="Content, embeddings, and free-form metadata are not part of this contract and are not shown."
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
      <label class="flex w-72 flex-col gap-1">
        <span class="ix-label">Session ID</span>
        <input
          v-model="sessionDraft"
          type="text"
          class="ix-input w-full font-mono text-xs"
          placeholder="Optional session UUID"
          autocomplete="off"
          :aria-invalid="Boolean(sessionError)"
          @keyup.enter="applySession"
          @blur="applySession"
        >
        <span v-if="sessionError" class="text-[0.6875rem] text-crit">{{ sessionError }}</span>
      </label>
      <label class="flex w-40 flex-col gap-1">
        <span class="ix-label">Status</span>
        <select class="ix-input" :value="state.status ?? ''" @change="onStatusChange">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="superseded">Superseded</option>
          <option value="merged_into">Merged</option>
          <option value="archived">Archived</option>
          <option value="quarantined">Quarantined</option>
          <option value="deleted">Deleted</option>
        </select>
      </label>
      <label class="flex w-40 flex-col gap-1">
        <span class="ix-label">Category</span>
        <select class="ix-input" :value="state.category ?? ''" @change="onCategoryChange">
          <option value="">All categories</option>
          <option value="factual">Factual</option>
          <option value="preference">Preference</option>
          <option value="behavioral">Behavioral</option>
          <option value="episodic">Episodic</option>
          <option value="procedural">Procedural</option>
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
      title="An operator session is required to read memories"
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
      title="Memory index unavailable"
      :body="failureDetail ?? 'The operator API did not return a verified snapshot.'"
    >
      <template #actions>
        <button type="button" class="ix-button-secondary" @click="refresh">Try again</button>
      </template>
    </IxVerdict>

    <IxVerdict
      v-else-if="!loading && memories.length === 0"
      tone="unknown"
      eyebrow="Live operator read"
      :title="hasFilters ? 'No memories match these filters' : 'No memories in this organization yet'"
      :body="
        hasFilters
          ? 'Clear or change the filters to widen the search. The API returned no rows for this query.'
          : 'Memories written by an agent appear here once the tenant has at least one.'
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
      <table class="ix-agent-table" aria-label="Memories">
        <caption class="sr-only">Metadata-only memory index for this organization.</caption>
        <thead>
          <tr>
            <th scope="col" class="!pl-4">Memory</th>
            <th scope="col" class="w-32">Category</th>
            <th scope="col" class="w-28">Status</th>
            <th scope="col" class="hidden w-28 min-[1000px]:table-cell">Source</th>
            <th scope="col" class="w-24 text-right">Tokens</th>
            <th scope="col" class="hidden w-24 text-right min-[1000px]:table-cell">Retrievals</th>
            <th scope="col" class="w-24">PII</th>
            <th scope="col" class="w-36">Created</th>
          </tr>
        </thead>
        <tbody>
          <template v-if="loading">
            <tr v-for="index in 5" :key="`skeleton-${index}`" aria-hidden="true">
              <td class="!pl-4"><span class="block h-3 w-48 animate-pulse rounded bg-raised" /></td>
              <td><span class="block h-3 w-20 animate-pulse rounded bg-raised" /></td>
              <td><span class="block h-3 w-16 animate-pulse rounded bg-raised" /></td>
              <td class="hidden min-[1000px]:table-cell"><span class="block h-3 w-20 animate-pulse rounded bg-raised" /></td>
              <td><span class="ml-auto block h-3 w-8 animate-pulse rounded bg-raised" /></td>
              <td class="hidden min-[1000px]:table-cell"><span class="ml-auto block h-3 w-8 animate-pulse rounded bg-raised" /></td>
              <td><span class="block h-3 w-12 animate-pulse rounded bg-raised" /></td>
              <td><span class="block h-3 w-20 animate-pulse rounded bg-raised" /></td>
            </tr>
          </template>
          <template v-else>
            <tr v-for="memory in memories" :key="memory.id" :data-memory-row="memory.id">
              <td class="!pl-4">
                <NuxtLink
                  :to="memoryHref(memory)"
                  class="block font-mono text-xs font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                >
                  {{ memory.id.slice(0, 8) }}…{{ memory.id.slice(-4) }}
                </NuxtLink>
                <span class="mt-0.5 block truncate font-mono text-[0.625rem] leading-4 text-fg-3">
                  agent {{ memory.agent_id.slice(0, 8) }}
                </span>
              </td>
              <td class="text-xs text-fg-2">{{ memory.category }}</td>
              <td><MemoryStatusPill :status="memory.status" /></td>
              <td class="hidden text-xs text-fg-2 min-[1000px]:table-cell">{{ memory.source }}</td>
              <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ formatGovernNumber(memory.content_tokens) }}</td>
              <td class="hidden text-right font-mono text-xs text-fg-1 tabular-nums min-[1000px]:table-cell">
                {{ formatGovernNumber(memory.retrieval_count) }}
              </td>
              <td class="text-xs" :class="memory.pii_detected ? 'text-warn' : 'text-fg-3'">
                {{ memory.pii_detected ? (memory.pii_redacted ? "Redacted" : "Flagged") : "None" }}
              </td>
              <td class="text-xs whitespace-nowrap text-fg-2">{{ formatGovernStamp(memory.created_at) }}</td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <nav v-if="!error && (memories.length > 0 || state.cursor)" class="flex flex-wrap items-center justify-between gap-2" aria-label="Memory pages">
      <p class="text-xs text-fg-3">Showing {{ memories.length }} memor{{ memories.length === 1 ? "y" : "ies" }} from the operator API.</p>
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
