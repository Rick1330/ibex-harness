<script setup lang="ts">
import { computed } from "vue"
import { Archive, Lock, ShieldAlert } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { formatDayTimeUtc } from "@/lib/format"
import { MEMORY_STATUS_LABELS, memoryRelativeTime } from "@/lib/memory-preview"
import type {
  MemoryDetail,
  MemoryLifecycleKind,
  MemoryVersion,
  MemoryVersionOperation,
} from "@/lib/memory-detail-preview"
import { diffWords } from "@/lib/text-diff"
import MemoryStatTile from "./primitives/MemoryStatTile.vue"

const props = defineProps<{ detail: MemoryDetail }>()

const readOnlyTooltip = "Read-only console. Requires a privileged write contract."
const diffsVisible = computed(() => props.detail.rawContentGate === "open")

type TimelineEntry = {
  id: string
  at: string
  badge: string
  badgeTone: string
  title: string
  note: string
  actor: string
  relatedId: string | null
  version: MemoryVersion | null
}

const BADGE_TONES: Record<string, string> = {
  CREATED: "border-transparent bg-transparent text-ok",
  UPDATED: "border-memory/40 bg-memory-tint text-memory",
  VERIFIED: "border-viz-2/40 text-viz-2",
  ARCHIVED: "border-line bg-raised text-fg-2",
  SUPERSEDED: "border-line bg-raised text-fg-2",
  MERGED: "border-line bg-raised text-fg-2",
  QUARANTINED: "border-transparent bg-transparent text-warn",
  DELETED: "border-transparent bg-transparent text-crit",
  CONFLICT: "border-transparent bg-transparent text-warn",
  "STATUS CHANGED": "border-line bg-raised text-fg-2",
  "CONFIDENCE UPDATED": "border-memory/40 bg-memory-tint text-memory",
}

const operationBadge: Record<MemoryVersionOperation, string> = {
  created: "CREATED",
  updated: "UPDATED",
  status_changed: "STATUS CHANGED",
  confidence_updated: "CONFIDENCE UPDATED",
  merged: "MERGED",
  deleted: "DELETED",
}

const lifecycleBadge: Record<MemoryLifecycleKind, string> = {
  created: "CREATED",
  superseded: "SUPERSEDED",
  merged: "MERGED",
  quarantined: "QUARANTINED",
  archived: "ARCHIVED",
  deleted: "DELETED",
  conflict_opened: "CONFLICT",
  confidence_updated: "CONFIDENCE UPDATED",
}

const timeline = computed<TimelineEntry[]>(() => {
  const fromVersions: TimelineEntry[] = props.detail.versions.map((version) => ({
    id: version.id,
    at: version.changedAt,
    badge: operationBadge[version.operation],
    badgeTone: BADGE_TONES[operationBadge[version.operation]] ?? "border-line bg-raised text-fg-2",
    title: version.reason,
    note: version.statusFrom && version.statusTo
      ? `${MEMORY_STATUS_LABELS[version.statusFrom]} → ${MEMORY_STATUS_LABELS[version.statusTo]}`
      : version.confidenceFrom !== null && version.confidenceTo !== null
        ? `Confidence ${version.confidenceFrom.toFixed(2)} → ${version.confidenceTo.toFixed(2)}`
        : "",
    actor: version.changedBy,
    relatedId: null,
    version,
  }))

  const fromLifecycle: TimelineEntry[] = props.detail.lifecycleEvents.map((event) => ({
    id: event.id,
    at: event.at,
    badge: lifecycleBadge[event.kind],
    badgeTone: BADGE_TONES[lifecycleBadge[event.kind]] ?? "border-line bg-raised text-fg-2",
    title: event.note,
    note: "",
    actor: event.actor,
    relatedId: event.relatedId,
    version: null,
  }))

  // Lifecycle events restate version ops with audit notes; keep one entry per (timestamp, badge).
  const seen = new Set(fromVersions.map((entry) => `${entry.at}|${entry.badge}`))
  const merged = [
    ...fromVersions,
    ...fromLifecycle.filter((entry) => !seen.has(`${entry.at}|${entry.badge}`)),
  ]
  return merged.sort((first, second) => Date.parse(second.at) - Date.parse(first.at))
})

const cascade = computed(() => [
  { label: "Versions", value: props.detail.versions.length },
  { label: "Lifecycle events", value: props.detail.lifecycleEvents.length },
  { label: "Relationships", value: props.detail.lineage.edges.length },
  { label: "Retrieval references", value: props.detail.retrieval.sessions.length },
])

function actorLabel(actor: string): string {
  return actor.replace(/^(agent|operator|user):/, "")
}
</script>

<template>
  <div class="min-w-0 space-y-6">
    <section aria-labelledby="memory-timeline" class="rounded-lg border border-line-subtle bg-surface">
      <div class="flex flex-wrap items-baseline justify-between gap-2 p-5 pb-3">
        <h2 id="memory-timeline" class="text-sm leading-5 font-semibold text-fg-1">History timeline</h2>
        <span class="flex items-center gap-2 text-xs leading-4 text-fg-3">
          {{ detail.versions.length }} {{ detail.versions.length === 1 ? "version" : "versions" }} · append-only · audit-backed
          <span class="inline-flex h-5.5 items-center gap-1 rounded-full border border-line bg-raised px-2 text-xs text-fg-2">
            <span class="font-mono tabular-nums">r{{ detail.lifecycleRevision }}</span>
            <span class="text-fg-3">(current)</span>
          </span>
        </span>
      </div>

      <ol v-if="timeline.length" class="border-t border-line-subtle px-5 py-4">
        <li v-for="entry in timeline" :key="entry.id" class="relative flex gap-3.5 pb-6 last:pb-0">
          <div class="absolute top-3.5 bottom-0 left-[0.3rem] w-px bg-line last:hidden" aria-hidden="true" />
          <span class="relative z-10 mt-1 size-2.5 shrink-0 rounded-full border-2 border-memory bg-surface" aria-hidden="true" />
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <span
                class="inline-flex h-4.5 items-center rounded px-1.5 font-mono text-[0.625rem] leading-none font-semibold tracking-[0.06em]"
                :class="entry.badgeTone"
              >{{ entry.badge }}</span>
              <p class="min-w-0 flex-1 text-[0.8125rem] leading-5 font-medium text-fg-1 text-pretty">{{ entry.title }}</p>
              <time :datetime="entry.at" class="font-mono text-xs text-fg-3 tabular-nums">{{ formatDayTimeUtc(entry.at) }}</time>
              <span class="text-[0.6875rem] text-fg-3">{{ memoryRelativeTime(entry.at) }}</span>
            </div>
            <p v-if="entry.note" class="mt-0.5 text-xs leading-4 text-fg-3">{{ entry.note }}</p>
            <p class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs leading-4 text-fg-3">
              <span>by <span class="font-medium text-fg-2">{{ actorLabel(entry.actor) }}</span></span>
              <template v-if="entry.relatedId">
                <span aria-hidden="true">·</span>
                <NuxtLink
                  :to="`/memories/${encodeURIComponent(entry.relatedId)}`"
                  class="font-mono underline decoration-line-strong underline-offset-3 hover:text-accent hover:decoration-accent"
                >
                  {{ entry.relatedId }}
                </NuxtLink>
              </template>
            </p>

            <div
              v-if="entry.version && diffsVisible && entry.version.operation !== 'created' && (entry.version.previousContent || entry.version.newContent)"
              class="mt-2 max-w-3xl rounded-lg border border-line-subtle bg-raised/50 p-3"
            >
              <p class="text-[0.6875rem] leading-4 font-medium tracking-[0.06em] text-fg-3 uppercase">Content change</p>
              <p class="mt-1.5 text-[0.8125rem] leading-5 text-fg-2 text-pretty">
                <template v-for="(token, index) in diffWords(entry.version.previousContent ?? '', entry.version.newContent ?? '')" :key="index">
                  <del v-if="token.type === 'removed'" class="rounded-sm bg-crit-tint px-0.5 text-fg-3 line-through decoration-crit/60">{{ token.text }}</del>
                  <ins v-else-if="token.type === 'added'" class="rounded-sm bg-ok-tint px-0.5 text-fg-1 no-underline">{{ token.text }}</ins>
                  <template v-else>{{ token.text }}</template>
                </template>
              </p>
            </div>
            <p
              v-else-if="entry.version && !diffsVisible && (entry.version.previousContent || entry.version.newContent)"
              class="mt-2 flex items-center gap-1.5 text-xs leading-4 text-fg-3"
            >
              <Lock :size="11" :stroke-width="1.75" aria-hidden="true" />
              Content comparison gated · privileged record
            </p>
          </div>
        </li>
      </ol>
      <p v-else class="border-t border-line-subtle p-5 text-[0.8125rem] leading-5 text-fg-2">
        No version history was returned for this record.
      </p>
    </section>

    <section
      aria-labelledby="memory-danger"
      class="overflow-hidden rounded-lg border border-crit/30"
    >
      <div class="flex items-center gap-2 border-b border-crit/30 bg-crit-tint px-5 py-2.5">
        <ShieldAlert :size="14" :stroke-width="1.75" class="text-crit" aria-hidden="true" />
        <h2 id="memory-danger" class="text-sm leading-5 font-semibold text-crit">Danger zone</h2>
      </div>
      <div class="p-5">
        <p class="max-w-[62ch] text-[0.8125rem] leading-5 text-fg-2 text-pretty">
          Archiving retires this record from retrieval while keeping it auditable. Permanent deletion follows the
          organization's retention policy and requires a privileged, audited write contract.
        </p>
        <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MemoryStatTile v-for="item in cascade" :key="item.label" :label="`${item.label} affected`" :value="String(item.value)" />
        </div>
        <div class="mt-4 flex flex-wrap items-center gap-2.5">
          <Tooltip :delay-duration="150">
            <TooltipTrigger as-child>
              <span tabindex="0">
                <button type="button" disabled class="ix-button-secondary h-8 gap-1.5 px-3 text-xs">
                  <Lock :size="12" :stroke-width="1.75" aria-hidden="true" />
                  Archive
                </button>
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" class="!max-w-64 !text-xs">{{ readOnlyTooltip }}</TooltipContent>
          </Tooltip>
          <Tooltip :delay-duration="150">
            <TooltipTrigger as-child>
              <span tabindex="0">
                <button type="button" disabled class="ix-button-secondary h-8 gap-1.5 border-crit/40 px-3 text-xs !text-crit">
                  <Lock :size="12" :stroke-width="1.75" aria-hidden="true" />
                  Delete
                </button>
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" class="!max-w-64 !text-xs">{{ readOnlyTooltip }}</TooltipContent>
          </Tooltip>
          <p class="text-xs leading-4 text-fg-3">
            <Archive :size="12" :stroke-width="1.75" class="mr-1 inline align-[-1px]" aria-hidden="true" />
            Neither action is available in this read-only preview.
          </p>
        </div>
      </div>
    </section>
  </div>
</template>
