<script setup lang="ts">
import { computed } from "vue"
import LiveSessionStatusPill from "./LiveSessionStatusPill.vue"
import { formatGovernStamp } from "@/lib/govern-format"
import {
  agentSecondaryLabel,
  SESSION_EXTRACTION_NOTE,
  sessionColumnVisible,
  shortId,
  type SessionColumnId,
  type SessionListRow,
} from "@/lib/session-list"

const props = defineProps<{
  rows: SessionListRow[]
  loading: boolean
  columns: SessionColumnId[]
  returnTo: string
  /** The agents read that names the Agent column did not return. */
  agentReadFailed: boolean
}>()

const showExtraction = computed(() => sessionColumnVisible(props.columns, "extraction"))
const showTokens = computed(() => sessionColumnVisible(props.columns, "tokens"))
const columnCount = computed(() => 5 + props.columns.length)

function sessionHref(row: SessionListRow): string {
  return `/sessions/${encodeURIComponent(row.id)}?return=${encodeURIComponent(props.returnTo)}`
}

function agentHref(row: SessionListRow): string {
  return `/agents/${encodeURIComponent(row.agentId)}?return=${encodeURIComponent(props.returnTo)}`
}
</script>

<template>
  <div class="overflow-x-auto rounded-lg border border-line-subtle bg-surface">
    <table class="ix-agent-table" aria-label="Sessions">
      <caption class="sr-only">
        Metadata-only session index for this organization. Activity is the later of the completion time and the update
        time, and the cell says which one it shows, plus the summed latency of the recorded turns. Extraction is the
        zero-based index of the last extracted turn, which is not a count or a completion ratio.
      </caption>
      <thead>
        <tr>
          <th scope="col" class="!pl-4">Session</th>
          <th scope="col">Agent</th>
          <th scope="col" class="w-32">Outcome</th>
          <th scope="col" class="w-44">Activity</th>
          <th scope="col" class="w-20 text-right">Turns</th>
          <th v-if="showExtraction" scope="col" class="w-28 text-right">Extracted to</th>
          <th v-if="showTokens" scope="col" class="w-32 text-right">Tokens</th>
        </tr>
      </thead>
      <tbody>
        <template v-if="loading">
          <tr v-for="index in 5" :key="`skeleton-${index}`" aria-hidden="true">
            <td :colspan="columnCount" class="!pl-4">
              <span class="block h-3 w-2/5 animate-pulse rounded bg-raised" />
            </td>
          </tr>
        </template>
        <template v-else>
          <tr v-for="row in rows" :key="row.id" :data-session-row="row.id">
            <td class="!pl-4">
              <NuxtLink
                :to="sessionHref(row)"
                class="block font-mono text-xs font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
              >
                {{ row.shortId }}
              </NuxtLink>
              <span
                class="mt-0.5 block max-w-[18rem] truncate font-mono text-[0.625rem] leading-4 text-fg-3"
                :title="row.meta"
              >{{ row.meta }}</span>
            </td>
            <td>
              <NuxtLink
                v-if="row.agentName"
                :to="agentHref(row)"
                class="block max-w-[14rem] truncate text-xs font-medium text-fg-1 underline-offset-3 hover:text-accent-memory hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
                :title="row.agentName"
              >
                {{ row.agentName }}
              </NuxtLink>
              <span v-else class="block font-mono text-[0.6875rem] text-fg-2" :title="row.agentId">
                {{ shortId(row.agentId) }}
              </span>
              <span class="mt-0.5 block truncate font-mono text-[0.625rem] leading-4 text-fg-3" :title="row.agentId">
                {{ agentSecondaryLabel(row, agentReadFailed) }}
              </span>
            </td>
            <td><LiveSessionStatusPill :status="row.status" /></td>
            <td>
              <span class="block text-xs whitespace-nowrap text-fg-2">{{ formatGovernStamp(row.activityAt) }}</span>
              <span class="mt-0.5 block font-mono text-[0.625rem] leading-4 whitespace-nowrap text-fg-3">
                {{ row.activityKind.toLowerCase() }} · {{ row.latencyLabel }} latency
              </span>
            </td>
            <td class="text-right font-mono text-xs text-fg-1 tabular-nums">
              {{ row.turnsLabel }}<span class="sr-only"> turns</span>
            </td>
            <td v-if="showExtraction" class="text-right">
              <span class="block font-mono text-xs text-fg-1 tabular-nums">{{ row.extractionLabel }}</span>
              <span
                class="mt-0.5 block text-[0.625rem] leading-4 whitespace-nowrap text-fg-3"
                :title="SESSION_EXTRACTION_NOTE"
              >{{ row.extractionNote }}</span>
            </td>
            <td v-if="showTokens" class="text-right font-mono text-xs whitespace-nowrap text-fg-1 tabular-nums">
              {{ row.tokensLabel }}<span class="sr-only"> input and output tokens</span>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
