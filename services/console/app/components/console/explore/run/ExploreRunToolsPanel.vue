<script setup lang="ts">
import { computed } from "vue"
import type { PublicOperatorTraceDetail } from "~~/shared/operator/public"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import { formatDuration } from "@/lib/format"
import { formatGovernNumber, formatGovernStampMillis } from "@/lib/govern-format"
import { EXPLORE_TRACE_DETAIL_CONTRACT } from "@/lib/explore-view"

const props = defineProps<{ detail: PublicOperatorTraceDetail }>()

const tools = computed(() => props.detail.tools)
const toolsUnavailable = computed(() => props.detail.unavailable_sections.includes("tools"))
const failedCount = computed(() => tools.value.filter((tool) => tool.error_code !== null || tool.status !== "ok").length)

function toolDuration(tool: PublicOperatorTraceDetail["tools"][number]): string {
  if (tool.started_at === null || tool.ended_at === null) return "Not recorded"
  const started = Date.parse(tool.started_at)
  const ended = Date.parse(tool.ended_at)
  if (!Number.isFinite(started) || !Number.isFinite(ended) || ended < started) return "Not recorded"
  return formatDuration(ended - started)
}
</script>

<template>
  <section class="min-w-0" aria-label="Tool calls">
    <GovernPendingData
      v-if="toolsUnavailable"
      title="Tool calls"
      :contract="EXPLORE_TRACE_DETAIL_CONTRACT"
      description="The contract marked tools unavailable for this run. Which calls it made is unknown, not zero."
    />

    <GovernEmptyState
      v-else-if="tools.length === 0"
      title="No tool calls recorded"
      reason="The detail contract returned an empty tool list for this run. That is a recorded answer: nothing was called through the tool surface."
      next-step="If a tool did run, the gap is in capture, not in this page — the evidence tab shows how complete this capture was."
    />

    <div v-else class="min-w-0">
      <p class="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
        <span class="text-xs font-medium text-fg-1">Tool calls</span>
        <span class="font-mono text-[0.6875rem] leading-4 text-fg-3">
          {{ formatGovernNumber(tools.length) }} recorded
          <span v-if="failedCount"> · {{ formatGovernNumber(failedCount) }} reported an error</span>
        </span>
      </p>
      <div class="min-w-0 ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
        <table class="ix-agent-table" style="min-width: 780px" aria-label="Tool calls table">
          <thead>
            <tr>
              <th scope="col">Tool</th>
              <th scope="col">Status</th>
              <th scope="col">Error</th>
              <th scope="col">Started</th>
              <th scope="col">Ended</th>
              <th scope="col" class="text-right">Duration</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(tool, index) in tools" :key="`${tool.tool_name}-${index}`">
              <td class="truncate font-mono text-xs text-fg-1" :title="tool.tool_name">{{ tool.tool_name }}</td>
              <td class="font-mono text-xs" :class="tool.status === 'ok' ? 'text-fg-2' : 'text-crit'">{{ tool.status }}</td>
              <td class="truncate font-mono text-xs" :class="tool.error_code ? 'text-crit' : 'text-fg-3'" :title="tool.error_code ?? ''">
                {{ tool.error_code ?? "None reported" }}
              </td>
              <td class="whitespace-nowrap font-mono text-xs text-fg-2" :title="formatGovernStampMillis(tool.started_at)">
                {{ formatGovernStampMillis(tool.started_at) }}
              </td>
              <td class="whitespace-nowrap font-mono text-xs text-fg-2" :title="formatGovernStampMillis(tool.ended_at)">
                {{ formatGovernStampMillis(tool.ended_at) }}
              </td>
              <td class="whitespace-nowrap text-right font-mono text-xs text-fg-2 tabular-nums">{{ toolDuration(tool) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="mt-1.5 text-[0.6875rem] leading-4 text-fg-3">
        Tool rows are listed in the order the contract returned them. Arguments and results are content, and content is
        outside this contract.
      </p>
    </div>
  </section>
</template>
