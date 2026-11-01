<script setup lang="ts">
import { computed, ref } from "vue"
import {
  ArrowUpRight,
  ChevronDown,
  Copy,
  Check,
  FileSearch,
  FolderOpen,
  GitBranch,
  ShieldAlert,
} from "@lucide/vue"
import { formatDayTimeUtc } from "@/lib/format"
import { MEMORY_CATEGORY_LABELS, MEMORY_SOURCE_LABELS, MEMORY_VISIBILITY_LABELS } from "@/lib/memory-preview"
import type { MemoryDetail, MemoryLineageEdge } from "@/lib/memory-detail-preview"
import MemoryInfoHint from "./primitives/MemoryInfoHint.vue"
import MemoryEmptyValue from "./primitives/MemoryEmptyValue.vue"
import MemoryCheckPill from "./primitives/MemoryCheckPill.vue"
import MemoryJsonView from "./primitives/MemoryJsonView.vue"
import MemoryPropertiesRail from "./MemoryPropertiesRail.vue"

const props = defineProps<{ detail: MemoryDetail; returnTo: string }>()
const emit = defineEmits<{ view: [value: "evidence" | "usage" | "history"] }>()

const memory = computed(() => props.detail.memory)
const gated = computed(() => props.detail.rawContentGate === "privileged")
const tombstoned = computed(() => props.detail.tombstoned)
const redacted = computed(() => props.detail.rawContentGate === "redacted")
const linkedSessions = computed(() => props.detail.retrieval.sessions)
const includedCount = computed(() => linkedSessions.value.filter((session) => session.usage === "injected").length)
const edges = computed(() => props.detail.lineage.edges.slice(0, 3))
const rawRecord = computed(() => ({
  id: memory.value.id,
  org_id: props.detail.orgId,
  status: memory.value.status,
  content: props.detail.rawContent ?? null,
  content_hash: props.detail.contentHash,
  category: memory.value.category,
  labels: memory.value.labels,
  confidence: memory.value.confidence,
  source: memory.value.source,
  agent_id: memory.value.agentId,
  visibility: memory.value.visibility,
  valid_from: memory.value.validFrom,
  valid_until: memory.value.validUntil,
  created_at: memory.value.createdAt,
  updated_at: memory.value.updatedAt,
  raw_content_gate: props.detail.rawContentGate,
  metadata: props.detail.metadata,
}))

const copiedJson = ref(false)
let jsonCopyTimer: ReturnType<typeof setTimeout> | null = null

async function copyJson(): Promise<void> {
  try {
    await navigator.clipboard.writeText(JSON.stringify(rawRecord.value, null, 2))
    copiedJson.value = true
  } catch {
    copiedJson.value = false
  }
  if (jsonCopyTimer) clearTimeout(jsonCopyTimer)
  jsonCopyTimer = setTimeout(() => {
    copiedJson.value = false
  }, 1_500)
}

const technicalRows = computed(() => [
  { label: "Memory ID", value: memory.value.id },
  { label: "Content hash", value: props.detail.contentHash },
  { label: "Organization", value: props.detail.orgId },
  { label: "Raw content gate", value: props.detail.rawContentGate },
  { label: "Created", value: formatDayTimeUtc(memory.value.createdAt) },
  { label: "Updated", value: formatDayTimeUtc(memory.value.updatedAt) },
  { label: "Embedding model", value: props.detail.embedding.model },
  { label: "Dimensions", value: String(props.detail.embedding.dimensions) },
])

function edgeLabel(edge: MemoryLineageEdge): string {
  if (edge.type === "supersedes") return edge.direction === "outgoing" ? "Supersedes" : "Superseded by"
  if (edge.type === "contradicts") return edge.direction === "outgoing" ? "Contradicts" : "Contradicted by"
  if (edge.type === "merged_from") return edge.direction === "outgoing" ? "Merged from" : "Merged into this record"
  if (edge.type === "derived_from") return edge.direction === "outgoing" ? "Derived from" : "Derived from this record"
  if (edge.type === "specializes") return edge.direction === "outgoing" ? "Specializes" : "Specialized by"
  return edge.direction === "outgoing" ? "Generalizes" : "Generalized by"
}

const funnelSteps = computed(() => [
  { label: "Retrieval events", value: props.detail.retrieval.count },
  { label: "Sessions", value: linkedSessions.value.length },
  { label: "Included in context", value: includedCount.value },
])

// Validity timeline: linear scale from effective-from to the latest known activity (capped at preview now).
const timeline = computed(() => {
  const start = Date.parse(memory.value.validFrom)
  const candidates = [
    memory.value.createdAt,
    memory.value.updatedAt,
    memory.value.lastRetrievedAt,
    props.detail.retrieval.lastRetrievedAt,
    memory.value.observedAt,
  ].filter((value): value is string => Boolean(value))
  const end = Math.max(...candidates.map((value) => Date.parse(value)), start + 1)
  const span = Math.max(1, end - start)

  function position(value: string | null): number | null {
    if (!value) return null
    return Math.min(100, Math.max(0, ((Date.parse(value) - start) / span) * 100))
  }

  return {
    startLabel: formatDayTimeUtc(memory.value.validFrom),
    markers: [
      { id: "created", label: "Created", at: memory.value.createdAt, left: position(memory.value.createdAt) ?? 0, hollow: false },
      ...(memory.value.lastRetrievedAt
        ? [{ id: "retrieved", label: "Last retrieved", at: memory.value.lastRetrievedAt, left: position(memory.value.lastRetrievedAt) ?? 0, hollow: false }]
        : []),
      {
        id: "verified",
        label: "Last verified",
        at: props.detail.lastVerifiedAt,
        left: props.detail.lastVerifiedAt ? (position(props.detail.lastVerifiedAt) ?? 0) : 100,
        hollow: !props.detail.lastVerifiedAt,
      },
    ],
    openEnded: !memory.value.validUntil,
  }
})
</script>

<template>
  <div class="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
    <div class="min-w-0 space-y-6">
      <section
        aria-labelledby="memory-statement"
        class="rounded-lg border border-line-subtle bg-surface p-6"
      >
        <h2 id="memory-statement" class="sr-only">Remembered statement</h2>

        <div v-if="gated" class="flex items-start gap-2.5 border-l-2 border-warn/60 pl-3">
          <ShieldAlert :size="16" :stroke-width="1.75" class="mt-0.5 shrink-0 text-warn" aria-hidden="true" />
          <div>
            <p class="text-sm leading-5 font-medium text-warn">Privileged content gated</p>
            <p class="mt-1 text-[0.8125rem] leading-5 text-fg-2 text-pretty">
              The raw statement is withheld until a human review resolves the quarantine. This record is excluded from
              retrieval.
            </p>
          </div>
        </div>

        <div v-else-if="tombstoned">
          <div class="flex items-start gap-2.5 border-l-2 border-crit/60 pl-3">
            <FileSearch :size="16" :stroke-width="1.75" class="mt-0.5 shrink-0 text-crit" aria-hidden="true" />
            <div>
              <p class="text-sm leading-5 font-medium text-fg-1">Content removed under a deletion request</p>
              <p class="mt-1 text-[0.8125rem] leading-5 text-fg-2 text-pretty">
                Only the lifecycle record and deletion receipt remain. The stored statement, source excerpt, and embedding
                are no longer available.
              </p>
            </div>
          </div>
          <p v-if="detail.deletionReceipt" class="mt-3 flex flex-wrap items-baseline gap-x-2 text-xs text-fg-3">
            <span>Deletion receipt</span>
            <span class="font-mono break-all text-fg-2">{{ detail.deletionReceipt }}</span>
          </p>
        </div>

        <template v-else>
          <p class="text-2xl leading-9 font-medium text-fg-1 text-pretty" aria-label="Remembered statement">
            <span class="mr-1 font-serif text-3xl leading-none text-fg-off select-none" aria-hidden="true">“</span>{{ memory.content }}<span class="font-serif text-3xl leading-none text-fg-off" aria-hidden="true">”</span>
          </p>
          <p v-if="redacted" class="mt-2 text-xs leading-4 text-warn">
            PII was redacted before storage. The stored text contains placeholders, not the original values.
          </p>
        </template>

        <div class="mt-4 flex flex-wrap items-center gap-1.5">
          <span class="ix-chip">{{ MEMORY_CATEGORY_LABELS[memory.category] }}</span>
          <span v-if="detail.appliesTo.length" class="ix-chip">Applies to: {{ detail.appliesTo.join(", ") }}</span>
          <span v-else class="ix-chip">Applies to: <MemoryEmptyValue /></span>
          <span class="ix-chip">Agent: {{ memory.agent }}</span>
          <span class="ix-chip">Visibility: {{ MEMORY_VISIBILITY_LABELS[memory.visibility] }}</span>
        </div>

        <p v-if="!gated && !tombstoned" class="mt-4 flex flex-wrap items-center gap-x-2 gap-y-0.5 border-t border-line-subtle pt-3 text-xs leading-4 text-fg-3">
          <span>Source · {{ MEMORY_SOURCE_LABELS[memory.source] }} statement</span>
          <template v-if="memory.sessionId">
            <span aria-hidden="true">·</span>
            <NuxtLink
              :to="`/sessions/${encodeURIComponent(memory.sessionId)}`"
              class="font-mono underline decoration-line-strong underline-offset-3 hover:text-accent hover:decoration-accent"
            >
              {{ memory.sessionId }}
            </NuxtLink>
          </template>
          <span aria-hidden="true">·</span>
          <span class="font-mono tabular-nums">{{ formatDayTimeUtc(memory.observedAt) }}</span>
          <template v-if="memory.sessionId">
            <span aria-hidden="true">·</span>
            <NuxtLink
              :to="`/sessions/${encodeURIComponent(memory.sessionId)}`"
              class="inline-flex items-center gap-0.5 underline decoration-line-strong underline-offset-3 hover:text-accent hover:decoration-accent"
            >
              Open source
              <ArrowUpRight :size="11" :stroke-width="1.75" aria-hidden="true" />
            </NuxtLink>
          </template>
        </p>
      </section>

      <section aria-labelledby="memory-validity" class="rounded-lg border border-line-subtle bg-surface p-5">
        <div class="flex items-baseline justify-between gap-2">
          <h2 id="memory-validity" class="text-sm leading-5 font-semibold text-fg-1">Validity timeline</h2>
          <span class="text-xs text-fg-3">Bi-temporal record</span>
        </div>
        <div class="mt-5 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3">
          <div class="text-right">
            <p class="text-xs leading-4 text-fg-3">Effective from</p>
            <p class="font-mono text-xs text-fg-1 tabular-nums">{{ timeline.startLabel }}</p>
          </div>
          <div class="relative h-8">
            <div class="absolute top-1/2 h-px w-full -translate-y-1/2 bg-line" aria-hidden="true" />
            <div
              v-if="timeline.openEnded"
              class="absolute top-1/2 right-0 h-px w-10 -translate-y-1/2 bg-gradient-to-r from-line to-transparent"
              aria-hidden="true"
            />
            <div
              v-for="marker in timeline.markers"
              :key="marker.id"
              class="absolute top-1/2 -translate-x-1/2 -translate-y-1/2"
              :style="{ left: `${marker.left}%` }"
            >
              <span
                class="block size-2.5 rounded-full border-2 bg-surface"
                :class="marker.hollow ? 'border-line-strong' : 'border-memory'"
                :title="`${marker.label}: ${marker.at ? formatDayTimeUtc(marker.at) : 'Not recorded in this record'}`"
                :aria-label="`${marker.label}: ${marker.at ? formatDayTimeUtc(marker.at) : 'not recorded'}`"
                role="img"
              />
              <span class="absolute top-4 left-1/2 -translate-x-1/2 text-[0.625rem] leading-3 whitespace-nowrap text-fg-3">
                {{ marker.label }}
              </span>
            </div>
          </div>
          <div>
            <p class="text-xs leading-4 text-fg-3">Expires</p>
            <p class="text-xs leading-4 text-fg-1">
              <MemoryEmptyValue v-if="timeline.openEnded" />
              <span v-else class="font-mono tabular-nums">{{ formatDayTimeUtc(memory.validUntil!) }}</span>
              <span v-if="timeline.openEnded" class="ml-1 text-fg-3">open-ended</span>
            </p>
          </div>
        </div>
      </section>

      <section aria-labelledby="memory-funnel" class="rounded-lg border border-line-subtle bg-surface p-5">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="memory-funnel" class="text-sm leading-5 font-semibold text-fg-1">Retrieval → context</h2>
          <button type="button" class="inline-flex items-center gap-1 text-xs font-medium text-fg-2 transition-colors hover:text-accent" @click="emit('view', 'usage')">
            See usage
            <ArrowUpRight :size="11" :stroke-width="1.75" aria-hidden="true" />
          </button>
        </div>
        <div class="mt-4 flex flex-col gap-2" style="max-width: 34rem">
          <div v-for="(step, index) in funnelSteps" :key="step.label" class="flex items-center gap-3">
            <span class="w-36 shrink-0 text-xs leading-4 text-fg-3">{{ step.label }}</span>
            <div class="h-6 flex-1 overflow-hidden rounded-md bg-raised" aria-hidden="true">
              <div
                class="flex h-full items-center justify-end rounded-md bg-memory px-2 transition-[width] duration-300"
                :style="{ width: `${Math.max(8, (step.value / Math.max(1, funnelSteps[0]!.value)) * 100)}%`, opacity: 1 - index * 0.22 }"
              />
            </div>
            <span class="w-8 shrink-0 text-right font-mono text-xs font-semibold text-fg-1 tabular-nums">{{ step.value }}</span>
          </div>
        </div>
        <p class="mt-3 flex items-center gap-1.5 text-xs leading-4 text-fg-3">
          {{ props.detail.retrieval.count }} retrieval events became {{ linkedSessions.length }} linked sessions; {{ includedCount }} placed this memory in context.
          <MemoryInfoHint label="About inclusion">
            <p class="font-medium text-fg-1">Inclusion is not influence</p>
            <p class="mt-1">
              A retrieval that placed this memory in the model context does not measure whether the final answer used it.
            </p>
          </MemoryInfoHint>
        </p>
      </section>

      <section aria-labelledby="memory-checks" class="rounded-lg border border-line-subtle bg-surface p-5">
        <div class="flex items-baseline justify-between gap-2">
          <h2 id="memory-checks" class="text-sm leading-5 font-semibold text-fg-1">Safety &amp; quality checks</h2>
          <MemoryInfoHint label="About these checks">
            <p class="font-medium text-fg-1">Not a safety certification</p>
            <p class="mt-1">
              These checks cover the stored text and indexing state only. A missing finding is not proof that no issue
              exists, and evaluation timestamps are not recorded in this preview.
            </p>
          </MemoryInfoHint>
        </div>
        <ul v-if="!tombstoned" class="mt-2 divide-y divide-line-subtle">
          <li v-for="check in detail.evaluation.checks" :key="check.id" class="flex items-center gap-3 py-2.5">
            <span class="min-w-0 flex-1">
              <span class="block text-[0.8125rem] leading-5 font-medium text-fg-1">{{ check.label }}</span>
              <span class="block truncate text-xs leading-4 text-fg-3">{{ check.detail }}</span>
            </span>
            <MemoryCheckPill :result="check.result" />
          </li>
        </ul>
        <p v-else class="mt-2 text-xs leading-4 text-fg-3 text-pretty">
          The content was deleted after evaluation. Retained check results are not shown because there is no stored text
          left to evaluate.
        </p>
      </section>

      <section aria-labelledby="memory-related" class="rounded-lg border border-line-subtle bg-surface p-5">
        <div class="flex items-baseline justify-between gap-2">
          <h2 id="memory-related" class="text-sm leading-5 font-semibold text-fg-1">Related memories</h2>
          <MemoryInfoHint label="About relationships">
            <p class="font-medium text-fg-1">About relationships</p>
            <p class="mt-1">
              Relationships are recorded edges only. An empty list does not prove that no conflicting memory exists.
            </p>
          </MemoryInfoHint>
        </div>
        <ul v-if="edges.length" class="mt-3 grid gap-2.5 sm:grid-cols-2">
          <li v-for="edge in edges" :key="edge.id">
            <NuxtLink
              :to="`/memories/${encodeURIComponent(edge.memoryId)}?return=${encodeURIComponent(returnTo)}`"
              class="block rounded-lg border border-line-subtle bg-raised/50 p-3 transition-colors hover:border-line hover:bg-raised"
            >
              <span class="flex items-center gap-1.5 text-[0.6875rem] font-medium text-fg-3">
                <GitBranch :size="11" :stroke-width="1.75" aria-hidden="true" />
                {{ edgeLabel(edge) }}
              </span>
              <span class="mt-1 line-clamp-2 block text-[0.8125rem] leading-5 font-medium text-fg-1">{{ edge.title }}</span>
              <span class="mt-1 block font-mono text-[0.625rem] text-fg-3">{{ edge.memoryId }}</span>
            </NuxtLink>
          </li>
        </ul>
        <div v-else class="mt-3 flex items-center gap-3 rounded-lg border border-dashed border-line px-4 py-4 text-fg-3">
          <FolderOpen :size="16" :stroke-width="1.75" class="shrink-0" aria-hidden="true" />
          <p class="text-[0.8125rem] leading-5">
            <span class="block font-medium text-fg-2">No linked memories</span>
            <span class="block text-xs leading-4 text-fg-3">No supersedes, conflict, or similarity edges are recorded for this memory.</span>
          </p>
        </div>
      </section>

      <details class="group rounded-lg border border-line-subtle bg-surface">
        <summary class="flex cursor-pointer list-none items-center justify-between gap-2 p-5 [&::-webkit-details-marker]:hidden">
          <span class="text-sm leading-5 font-semibold text-fg-1">Technical details</span>
          <ChevronDown :size="14" :stroke-width="1.75" class="text-fg-3 transition-transform group-open:rotate-180" aria-hidden="true" />
        </summary>
        <div class="border-t border-line-subtle p-5">
          <dl class="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
            <div v-for="row in technicalRows" :key="row.label" class="min-w-0">
              <dt class="text-xs leading-4 text-fg-3">{{ row.label }}</dt>
              <dd class="font-mono text-xs leading-5 text-fg-2 break-all">{{ row.value }}</dd>
            </div>
          </dl>
          <div class="mt-4">
            <p class="text-xs leading-4 text-fg-3">Record metadata</p>
            <dl class="mt-1.5 divide-y divide-line-subtle">
              <div v-for="(value, key) in detail.metadata" :key="key" class="grid grid-cols-[9rem_minmax(0,1fr)] gap-3 py-1.5">
                <dt class="font-mono text-xs leading-4 text-fg-3">{{ key }}</dt>
                <dd class="min-w-0 font-mono text-xs leading-4 text-fg-2 break-all">
                  {{ Array.isArray(value) ? value.join(", ") : typeof value === "object" ? JSON.stringify(value) : (value ?? "—") }}
                </dd>
              </div>
            </dl>
          </div>
          <div class="mt-4">
            <div class="flex items-center justify-between gap-2">
              <p class="text-xs leading-4 text-fg-3">Raw JSON</p>
              <button
                v-if="!tombstoned"
                type="button"
                class="inline-flex h-7 items-center gap-1.5 rounded-md border border-line bg-surface px-2 text-xs text-fg-2 transition-colors hover:border-line-strong hover:text-fg-1"
                @click="copyJson"
              >
                <Check v-if="copiedJson" :size="12" :stroke-width="2" class="text-ok" aria-hidden="true" />
                <Copy v-else :size="12" :stroke-width="1.75" aria-hidden="true" />
                {{ copiedJson ? "Copied" : "Copy JSON" }}
              </button>
            </div>
            <div class="mt-1.5">
              <MemoryJsonView v-if="!tombstoned" :value="rawRecord" />
              <p v-else class="rounded-lg border border-dashed border-line px-3 py-2.5 text-xs leading-4 text-fg-3">
                Raw record withheld · {{ detail.rawContentGate }} gate. The tombstone retains lifecycle metadata only.
              </p>
            </div>
          </div>
        </div>
      </details>
    </div>

    <aside class="min-w-0 xl:sticky xl:top-[6.75rem]" aria-label="Record properties">
      <MemoryPropertiesRail :detail="detail" />
    </aside>
  </div>
</template>

<style scoped>
.ix-chip {
  display: inline-flex;
  min-height: 1.375rem;
  align-items: center;
  gap: 0.25rem;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 9999px;
  padding: 0 0.5rem;
  font-size: 0.6875rem;
  line-height: 1;
  color: var(--ix-fg-2);
  white-space: nowrap;
}
</style>
