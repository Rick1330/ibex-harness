<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { RefreshCw, Search, Tag, X } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import AgentStatusPill from "../AgentStatusPill.vue"
import { useOperatorAgents } from "@/composables/useOperatorData"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import { formatLiveRelative } from "@/lib/live-format"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import {
  serializeLiveAgentQuery,
  type LiveAgentQuery,
  type LiveAgentStatus,
} from "~~/shared/operator/agent-query"
import type { OperatorAgent } from "~~/shared/operator/contracts"

const props = defineProps<{ state: LiveAgentQuery; returnTo: string }>()
const emit = defineEmits<{ update: [state: LiveAgentQuery] }>()

const agentsState = useOperatorAgents(() => serializeLiveAgentQuery(props.state))
const agents = computed<OperatorAgent[]>(() => agentsState.data.value?.data ?? [])
const pagination = computed(() => agentsState.data.value?.pagination ?? null)
const error = computed(() => agentsState.error.value)
const pending = computed(() => agentsState.status.value === "pending")
const loading = computed(() => pending.value && !agentsState.data.value && !error.value)
const authIssue = computed(() => isOperatorAuthError(error.value))
const failureDetail = computed(() =>
  error.value && !authIssue.value ? operatorFailureDetail(error.value) : null,
)

const hasFilters = computed(() =>
  Boolean(props.state.search || props.state.status || props.state.tags.length),
)
const emptyBecauseCursor = computed(
  () => agents.value.length === 0 && Boolean(props.state.cursor) && !hasFilters.value,
)
const activeCount = computed(() => agents.value.filter((agent) => agent.status === "active").length)
const verdict = computed(() => {
  if (loading.value) return "Reading the agent inventory…"
  if (authIssue.value) return "The operator session cannot read this organization"
  if (error.value) return "Agent inventory unavailable"
  if (agents.value.length === 0) {
    if (emptyBecauseCursor.value) return "No agents on this page"
    return hasFilters.value ? "No agents match these filters" : "No agents in this organization yet"
  }
  return `${agents.value.length} agents on this page · ${activeCount.value} active`
})
const coverage = computed(() => {
  if (error.value) return "No data shown"
  if (loading.value) return "Reading live data"
  return `${agents.value.length} live rows`
})

const nowMs = ref<number | null>(null)
let clock: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  nowMs.value = Date.now()
  clock = setInterval(() => {
    nowMs.value = Date.now()
  }, 30_000)
})
onBeforeUnmount(() => {
  if (clock) clearInterval(clock)
})

const searchDraft = ref(props.state.search ?? "")
const tagDraft = ref(props.state.tags.join(","))
let searchTimer: ReturnType<typeof setTimeout> | null = null

watch(
  () => props.state.search,
  (value) => {
    if ((value ?? "") !== searchDraft.value) searchDraft.value = value ?? ""
  },
)
watch(
  () => props.state.tags,
  (tags) => {
    const next = tags.join(",")
    if (next !== tagDraft.value) tagDraft.value = next
  },
)

function emitFilter(patch: Partial<LiveAgentQuery>): void {
  emit("update", { ...props.state, ...patch, cursor: null })
}

function onSearchInput(event: Event): void {
  const value = (event.target as HTMLInputElement).value
  searchDraft.value = value
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    const search = value.trim() || null
    if (search !== props.state.search) emitFilter({ search })
  }, 250)
}

function submitSearch(): void {
  if (searchTimer) clearTimeout(searchTimer)
  const search = searchDraft.value.trim() || null
  if (search !== props.state.search) emitFilter({ search })
}

function onStatusChange(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  const next = value ? (value as LiveAgentStatus) : null
  if (next !== props.state.status) emitFilter({ status: next })
}

function applyTags(): void {
  const tags = [...new Set(tagDraft.value.split(",").map((tag) => tag.trim()).filter(Boolean))]
  if (tags.join(",") !== props.state.tags.join(",")) emitFilter({ tags })
}

function clearFilters(): void {
  searchDraft.value = ""
  tagDraft.value = ""
  emit("update", { ...props.state, search: null, status: null, tags: [], cursor: null })
}

function agentHref(agent: OperatorAgent): string {
  return `/agents/${encodeURIComponent(agent.id)}?return=${encodeURIComponent(props.returnTo)}`
}

function providerLabel(agent: OperatorAgent): string {
  if (!agent.default_provider) return "Not set"
  return agent.default_model ? `${agent.default_provider} · ${agent.default_model}` : agent.default_provider
}

function refresh(): void {
  void agentsState.refresh()
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-5">
    <ConsolePageHeader
      title="Agents"
      definition="The tenant-scoped agent inventory: identity, status, provider, usage counters, and last activity."
      state="live"
      :verdict="verdict"
      contract="operator.agents.v1"
      scope="Organization"
      :range="state.cursor ? 'Cursor page' : 'First page'"
      :coverage="coverage"
      :caveat="'Health, budget, environment, owner, and drift are not part of this contract and are not shown.'"
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

    <form class="flex flex-wrap items-end gap-2" role="search" @submit.prevent="submitSearch">
      <label class="flex min-w-56 flex-1 flex-col gap-1">
        <span class="ix-label">Search</span>
        <span class="relative">
          <Search
            :size="14"
            :stroke-width="2"
            class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3"
            aria-hidden="true"
          />
          <input
            :value="searchDraft"
            type="search"
            class="ix-input w-full pl-8"
            placeholder="Name or slug"
            autocomplete="off"
            @input="onSearchInput"
          >
        </span>
      </label>
      <label class="flex w-44 flex-col gap-1">
        <span class="ix-label">Status</span>
        <select class="ix-input" :value="state.status ?? ''" @change="onStatusChange">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="paused">Paused</option>
          <option value="suspended">Suspended</option>
          <option value="archived">Archived</option>
        </select>
      </label>
      <label class="flex w-56 flex-col gap-1">
        <span class="ix-label">Tags</span>
        <span class="relative">
          <Tag
            :size="14"
            :stroke-width="2"
            class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3"
            aria-hidden="true"
          />
          <input
            v-model="tagDraft"
            type="text"
            class="ix-input w-full pl-8"
            placeholder="prod, billing"
            autocomplete="off"
            @keyup.enter="applyTags"
            @blur="applyTags"
          >
        </span>
      </label>
      <button
        v-if="hasFilters"
        type="button"
        class="ix-button-secondary inline-flex items-center gap-1.5"
        @click="clearFilters"
      >
        <X :size="13" :stroke-width="2" aria-hidden="true" />
        Clear
      </button>
    </form>

    <IxVerdict
      v-if="authIssue"
      tone="unavailable"
      eyebrow="Live operator read"
      title="An operator session is required to read agents"
      body="Sign in to the console with a session that can read this organization. No fixture rows are substituted."
    >
      <template #actions>
        <button type="button" class="ix-button-secondary" @click="refresh">Try again</button>
      </template>
    </IxVerdict>

    <IxVerdict
      v-else-if="error"
      tone="unavailable"
      eyebrow="Live operator read"
      title="Agent inventory unavailable"
      :body="failureDetail ?? 'The operator API did not return a verified snapshot.'"
    >
      <template #actions>
        <button type="button" class="ix-button-secondary" @click="refresh">Try again</button>
      </template>
    </IxVerdict>

    <IxVerdict
      v-else-if="!loading && agents.length === 0"
      tone="unknown"
      eyebrow="Live operator read"
      :title="
        emptyBecauseCursor
          ? 'No agents on this page'
          : hasFilters
            ? 'No agents match these filters'
            : 'No agents in this organization yet'
      "
      :body="
        emptyBecauseCursor
          ? 'This cursor page is empty, but earlier pages may still contain agents.'
          : hasFilters
            ? 'Clear or change the filters to widen the search. The API returned no rows for this query.'
            : 'Agents created through the API appear here once the tenant has at least one.'
      "
    >
      <template #actions>
        <button
          v-if="state.cursor"
          type="button"
          class="ix-button-secondary"
          @click="emit('update', { ...state, cursor: null })"
        >
          First page
        </button>
        <button v-if="hasFilters" type="button" class="ix-button-secondary" @click="clearFilters">
          Clear filters
        </button>
      </template>
    </IxVerdict>

    <div v-else class="overflow-x-auto rounded-lg border border-line-subtle bg-surface">
      <table class="ix-agent-table" aria-label="Agents">
        <caption class="sr-only">
          Agent inventory for this organization, one row per agent.
        </caption>
        <thead>
          <tr>
            <th scope="col" class="!pl-4">Agent</th>
            <th scope="col" class="w-28">Status</th>
            <th scope="col" class="w-48">Provider</th>
            <th scope="col" class="hidden w-56 min-[1100px]:table-cell">Tags</th>
            <th scope="col" class="w-24 text-right">Sessions</th>
            <th scope="col" class="hidden w-24 text-right min-[900px]:table-cell">Memories</th>
            <th scope="col" class="hidden w-28 text-right min-[1100px]:table-cell">Tokens</th>
            <th scope="col" class="w-36">Last active</th>
            <th scope="col" class="hidden w-28 min-[1100px]:table-cell">Created</th>
          </tr>
        </thead>
        <tbody>
          <template v-if="loading">
            <tr v-for="index in 5" :key="`skeleton-${index}`" aria-hidden="true">
              <td class="!pl-4">
                <span class="block h-3 w-40 animate-pulse rounded bg-raised" />
                <span class="mt-1 block h-2.5 w-24 animate-pulse rounded bg-raised" />
              </td>
              <td><span class="block h-3 w-16 animate-pulse rounded bg-raised" /></td>
              <td><span class="block h-3 w-28 animate-pulse rounded bg-raised" /></td>
              <td class="hidden min-[1100px]:table-cell"><span class="block h-3 w-24 animate-pulse rounded bg-raised" /></td>
              <td><span class="ml-auto block h-3 w-8 animate-pulse rounded bg-raised" /></td>
              <td class="hidden min-[900px]:table-cell"><span class="ml-auto block h-3 w-8 animate-pulse rounded bg-raised" /></td>
              <td class="hidden min-[1100px]:table-cell"><span class="ml-auto block h-3 w-12 animate-pulse rounded bg-raised" /></td>
              <td><span class="block h-3 w-20 animate-pulse rounded bg-raised" /></td>
              <td class="hidden min-[1100px]:table-cell"><span class="block h-3 w-20 animate-pulse rounded bg-raised" /></td>
            </tr>
          </template>
          <template v-else>
            <tr v-for="agent in agents" :key="agent.id" :data-agent-row="agent.id">
            <td class="!pl-4">
              <NuxtLink
                :to="agentHref(agent)"
                class="block max-w-80 truncate text-sm font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
              >
                {{ agent.name }}
              </NuxtLink>
              <span class="mt-0.5 block truncate font-mono text-[0.6875rem] leading-4 text-fg-3">
                {{ agent.slug }}
              </span>
            </td>
            <td>
              <AgentStatusPill :status="agent.status" />
            </td>
            <td class="truncate text-xs text-fg-2">{{ providerLabel(agent) }}</td>
            <td class="hidden min-[1100px]:table-cell">
              <span v-if="agent.tags.length === 0" class="text-xs text-fg-3">None</span>
              <span v-else class="flex flex-wrap gap-1">
                <span
                  v-for="tag in agent.tags.slice(0, 3)"
                  :key="tag"
                  class="rounded-full border border-line bg-raised px-1.5 font-mono text-[0.625rem] leading-4 text-fg-2"
                >
                  {{ tag }}
                </span>
                <span v-if="agent.tags.length > 3" class="text-[0.625rem] leading-4 text-fg-3">
                  +{{ agent.tags.length - 3 }}
                </span>
              </span>
            </td>
            <td class="text-right font-mono text-xs text-fg-1 tabular-nums">
              {{ formatGovernNumber(agent.total_sessions) }}
            </td>
            <td class="hidden text-right font-mono text-xs text-fg-1 tabular-nums min-[900px]:table-cell">
              {{ formatGovernNumber(agent.total_memories) }}
            </td>
            <td class="hidden text-right font-mono text-xs text-fg-1 tabular-nums min-[1100px]:table-cell">
              {{ formatGovernNumber(agent.total_tokens_used) }}
            </td>
            <td class="text-xs whitespace-nowrap text-fg-2">
              <span :title="formatGovernStamp(agent.last_active_at)">
                {{ formatLiveRelative(agent.last_active_at, nowMs) }}
              </span>
            </td>
            <td class="hidden text-xs whitespace-nowrap text-fg-2 min-[1100px]:table-cell">
              {{ formatGovernStamp(agent.created_at) }}
            </td>
          </tr>
          </template>
        </tbody>
      </table>
    </div>

    <nav
      v-if="!error && (agents.length > 0 || state.cursor)"
      class="flex flex-wrap items-center justify-between gap-2"
      aria-label="Agent pages"
    >
      <p class="text-xs text-fg-3">
        Showing {{ agents.length }} agent{{ agents.length === 1 ? "" : "s" }} from the operator API.
      </p>
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
