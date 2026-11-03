<script setup lang="ts">
import { computed } from "vue"
import type { PublicOperatorTraceDetail } from "~~/shared/operator/public"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import { formatDuration } from "@/lib/format"
import { formatGovernRelative, formatGovernStampSeconds } from "@/lib/govern-format"
import {
  SECTION_LABELS,
  SECTION_MEANING,
  isUnavailableSection,
} from "@/lib/explore-view"

const props = defineProps<{ detail: PublicOperatorTraceDetail }>()

const detail = computed(() => props.detail)

/**
 * Only quantities and timestamps are tiled here. Status, completeness and publication are words,
 * and the header chips, the status line and the Evidence section already carry them with meanings.
 */
const tiles = computed(() => [
  {
    label: "Duration",
    value: detail.value.duration_ms === null ? "Not recorded" : formatDuration(detail.value.duration_ms),
    helper: "The proxy's own figure for this run.",
    tone: detail.value.duration_ms === null ? ("warning" as const) : ("default" as const),
  },
  {
    label: "Started",
    value: formatGovernStampSeconds(detail.value.started_at),
    helper: `${formatGovernRelative(detail.value.started_at, detail.value.evidence.observed_at)} · as recorded by the proxy.`,
    tone: "default" as const,
  },
  {
    label: "Ended",
    value: detail.value.ended_at === null ? "Not recorded" : formatGovernStampSeconds(detail.value.ended_at),
    helper: detail.value.ended_at === null
      ? "No end was written for this run."
      : `${formatGovernRelative(detail.value.ended_at, detail.value.evidence.observed_at)} · the duration above is the proxy's own figure, not this minus the start.`,
    tone: detail.value.ended_at === null ? ("warning" as const) : ("default" as const),
  },
  {
    label: "Evidence observed",
    value: formatGovernStampSeconds(detail.value.evidence.observed_at),
    helper: "When the platform read this evidence row.",
    tone: "default" as const,
  },
])

const identityRows = computed(() => [
  { key: "run", label: "Run id", value: detail.value.run_id },
  { key: "trace", label: "Trace id", value: detail.value.trace_id },
  { key: "request", label: "Request id", value: detail.value.request_id },
  { key: "agent", label: "Agent id", value: detail.value.agent_id },
  { key: "session", label: "Session id", value: detail.value.session_id },
  { key: "checkpoint", label: "Checkpoint id", value: detail.value.checkpoint_id },
])

const unavailable = computed(() => detail.value.unavailable_sections)
</script>

<template>
  <section class="flex min-w-0 flex-col gap-3" aria-label="Run overview">
    <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <GovernStatTile
        v-for="tile in tiles"
        :key="tile.label"
        :label="tile.label"
        :value="tile.value"
        :helper="tile.helper"
        :tone="tile.tone"
      />
    </div>

    <div class="min-w-0 rounded-lg border border-line-subtle bg-surface">
      <p class="border-b border-line-subtle px-3.5 py-2 text-xs font-medium text-fg-1">Identifiers, as recorded</p>
      <dl class="divide-y divide-line-subtle px-3.5">
        <div v-for="row in identityRows" :key="row.key" class="flex items-baseline justify-between gap-3 py-1.5">
          <dt class="shrink-0 text-[0.6875rem] text-fg-3">{{ row.label }}</dt>
          <dd class="min-w-0 text-right">
            <GovernCopyId v-if="row.value" :id="row.value" :label="row.label" truncate />
            <span v-else class="font-mono text-[0.6875rem] leading-5 text-fg-3">Not recorded</span>
          </dd>
        </div>
      </dl>
      <p class="border-t border-line-subtle px-3.5 py-2 text-[0.6875rem] leading-4 text-fg-3">
        These are identifiers only. The agent, session and memory surfaces in this build read from a preview set, so a
        live id has no record to open there yet.
      </p>
    </div>

    <div class="min-w-0 rounded-lg border border-dashed border-line bg-surface px-3.5 py-3">
      <p class="text-xs font-medium text-fg-1">
        {{ unavailable.length ? "Sections this run did not return" : "Every section this contract can supply was returned" }}
      </p>
      <ul v-if="unavailable.length" class="mt-2 flex flex-col gap-1.5">
        <li v-for="section in unavailable" :key="section" class="flex items-baseline gap-2 text-[0.6875rem] leading-4">
          <span class="shrink-0 rounded-full border border-line-subtle px-2 font-mono text-fg-2">
            {{ isUnavailableSection(section) ? SECTION_LABELS[section] : section }}
          </span>
          <span class="min-w-0 text-fg-3">
            {{ isUnavailableSection(section) ? SECTION_MEANING[section] : "Named by the contract but not described in this build." }}
          </span>
        </li>
      </ul>
      <p v-else class="mt-1 text-[0.6875rem] leading-4 text-fg-3">
        An empty list here is the contract's own statement, not the absence of one. Content is excluded by policy and is
        listed separately in the timeline note.
      </p>
    </div>
  </section>
</template>
