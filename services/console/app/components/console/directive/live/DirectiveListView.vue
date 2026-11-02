<script setup lang="ts">
import { computed } from "vue"
import { ArrowRight, RefreshCw } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import { useOperatorDirectives } from "@/composables/useOperatorData"
import { formatGovernRelative, formatGovernStamp } from "@/lib/govern-format"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import {
  directiveStateLabel,
  injectionModeLabel,
} from "@/lib/directive-summary"
import {
  DIRECTIVE_STATES,
  serializeLiveDirectiveListQuery,
  type DirectiveStateFilter,
  type LiveDirectiveListQuery,
} from "~~/shared/operator/directive-query"

const props = defineProps<{ state: LiveDirectiveListQuery; returnTo: string }>()
const emit = defineEmits<{ update: [state: LiveDirectiveListQuery] }>()

const directivesState = useOperatorDirectives(() => serializeLiveDirectiveListQuery(props.state))
const directives = computed(() => directivesState.data.value?.data ?? [])
const pagination = computed(() => directivesState.data.value?.pagination ?? null)
const error = computed(() => directivesState.error.value)
const authIssue = computed(() => isOperatorAuthError(error.value))
const failureDetail = computed(() =>
  error.value && !authIssue.value ? operatorFailureDetail(error.value) : null,
)
const loading = computed(
  () => directivesState.status.value === "pending" && !directivesState.data.value && !error.value,
)

const stateOptions = DIRECTIVE_STATES.map((value) => ({
  value,
  label: value === "all" ? "All directives" : value === "active" ? "Active only" : "Inactive only",
}))

const hasFilters = computed(() => props.state.state !== "all")

const verdict = computed(() => {
  if (loading.value) return "Reading the directive index…"
  if (authIssue.value) return "The operator session cannot read this organization"
  if (error.value) return "Directive index unavailable"
  if (!directives.value.length) {
    return hasFilters.value ? "No directives match this filter" : "No agent directive exists yet"
  }
  const live = directives.value.filter(
    (directive) => directive.is_active && directive.active_version_num !== null,
  ).length
  return `${directives.value.length} directive(s); ${live} resolve to a published version`
})

const coverage = computed(() => {
  if (error.value) return "No data shown"
  if (loading.value) return "Reading live data"
  return `${directives.value.length} live rows`
})

const newest = computed(() => {
  const stamps = directives.value
    .map((directive) => directive.last_version_at)
    .filter((value): value is string => value !== null)
    .sort((left, right) => Date.parse(right) - Date.parse(left))
  return stamps[0] ?? null
})

const notes = [
  {
    lead: "Live means the pointer, not the newest version.",
    body: "A rollback moves the pointer back to an older version; it does not create a version. The live version is whatever the pointer names, even when a newer version exists.",
  },
  {
    lead: "Instruction text is not in this contract.",
    body: "Versions are identified by number, digest prefix, and size. Reading the text, or diffing two versions, needs a separate contract behind the redacted-read permission.",
  },
  {
    lead: "Promotion history needs a write path.",
    body: "The console is read-only, so no promotion or rollback events exist to show yet. The audit and promotion tabs say so rather than inventing a history.",
  },
]

function update(patch: Partial<LiveDirectiveListQuery>): void {
  emit("update", { ...props.state, ...patch, cursor: null })
}

function detailHref(directiveId: string): string {
  return `/directives/${encodeURIComponent(directiveId)}?return=${encodeURIComponent(props.returnTo)}`
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      title="Directives"
      definition="Which instruction version a new session would resolve to, which versions exist, and where the pointer has moved."
      state="live"
      :verdict="verdict"
      contract="operator.directives.versions.v1"
      scope="Organization"
      range="Latest change per agent"
      :coverage="coverage"
      :observed="newest"
      caveat="Instruction text and diffs are not part of this contract. A live version means the pointer names it, not that its content was read."
      :notes="notes"
    >
      <template #actions>
        <GovernFilterSelect
          label="State"
          :model-value="state.state"
          :options="stateOptions"
          default-value="all"
          @update:model-value="update({ state: $event as DirectiveStateFilter })"
        />
      </template>
    </ConsolePageHeader>

    <IxVerdict
      v-if="loading"
      tone="unknown"
      eyebrow="Live operator read"
      title="Reading the directive index"
      body="Asking the operator API for this organization's directives."
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
      title="Directive index unavailable"
      :body="failureDetail ?? 'The upstream read failed. No values are inferred.'"
    />
    <IxVerdict
      v-else-if="!directives.length"
      tone="unknown"
      eyebrow="Live operator read"
      :title="hasFilters ? 'No directives match this filter' : 'No agent directive exists yet'"
      :body="
        hasFilters
          ? 'Clear the state filter to see every directive in this organization.'
          : 'A directive is created with its agent. Nothing is inferred for an agent without one.'
      "
    />

    <template v-else>
      <div class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
        <table class="ix-agent-table table-fixed" style="min-width: 860px" aria-label="Directives">
          <thead>
            <tr>
              <th scope="col" style="width: 260px">Agent</th>
              <th scope="col" style="width: 150px">Live version</th>
              <th scope="col" style="width: 90px" class="text-right">Versions</th>
              <th scope="col" style="width: 180px">Injection</th>
              <th scope="col" style="width: 130px">Last version</th>
              <th scope="col" style="width: 70px"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="directive in directives" :key="directive.id">
              <td>
                <p class="truncate text-xs font-medium text-fg-1">{{ directive.agent_name }}</p>
                <p class="mt-0.5 truncate font-mono text-[0.625rem] leading-4 text-fg-3">
                  {{ directive.agent_slug }}
                </p>
              </td>
              <td>
                <span
                  class="text-xs"
                  :class="directive.active_version_num === null ? 'text-fg-3' : 'text-fg-1'"
                >
                  {{ directiveStateLabel(directive) }}
                </span>
              </td>
              <td class="text-right font-mono tabular-nums text-xs text-fg-2">
                {{ directive.version_count }}
              </td>
              <td class="truncate text-xs text-fg-2">{{ injectionModeLabel(directive.injection_mode) }}</td>
              <td>
                <span
                  v-if="directive.last_version_at"
                  class="text-xs text-fg-2"
                  :title="formatGovernStamp(directive.last_version_at)"
                >
                  {{ formatGovernRelative(directive.last_version_at, directive.updated_at) }}
                </span>
                <span v-else class="text-xs text-fg-3">No version</span>
              </td>
              <td class="text-right">
                <NuxtLink
                  :to="detailHref(directive.id)"
                  class="inline-flex items-center gap-1 text-xs text-fg-3 hover:text-fg-1"
                >
                  Open
                  <ArrowRight :size="12" :stroke-width="1.9" aria-hidden="true" />
                </NuxtLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="flex flex-wrap items-center gap-3 text-[0.6875rem] text-fg-3">
        <NuxtLink
          v-if="pagination?.next_cursor"
          :to="{ query: { ...$route.query, cursor: pagination.next_cursor } }"
          class="inline-flex items-center gap-1 hover:text-fg-1"
        >
          <RefreshCw :size="12" :stroke-width="1.9" aria-hidden="true" />
          Next page
        </NuxtLink>
        <NuxtLink
          v-else-if="state.cursor"
          :to="{ query: { ...$route.query, cursor: undefined } }"
          class="inline-flex items-center gap-1 hover:text-fg-1"
        >
          First page
        </NuxtLink>
      </div>
    </template>
  </div>
</template>
