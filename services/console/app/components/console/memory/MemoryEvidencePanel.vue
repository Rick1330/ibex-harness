<script setup lang="ts">
import { computed } from "vue"
import {
  AlertTriangle,
  ArrowUpRight,
  Bot,
  Check as CheckIcon,
  Database,
  FileSearch,
  ScanSearch,
  ShieldAlert,
  Tags,
} from "@lucide/vue"
import { formatDayTimeUtc } from "@/lib/format"
import { MEMORY_SOURCE_LABELS, memoryInjectionBand } from "@/lib/memory-preview"
import { previewSessions } from "@/lib/session-preview"
import type { MemoryDetail, MemoryLineageEdge } from "@/lib/memory-detail-preview"
import MemoryInfoHint from "./primitives/MemoryInfoHint.vue"
import MemoryEmptyValue from "./primitives/MemoryEmptyValue.vue"
import MemoryCheckPill from "./primitives/MemoryCheckPill.vue"
import MemoryScoreBar from "./primitives/MemoryScoreBar.vue"
import MemoryCompleteness from "./primitives/MemoryCompleteness.vue"
import MemoryStatusPill from "./primitives/MemoryStatusPill.vue"

const props = defineProps<{ detail: MemoryDetail; returnTo: string }>()

const memory = computed(() => props.detail.memory)
const sourceSession = computed(() =>
  memory.value.sessionId && previewSessions.some((session) => session.id === memory.value.sessionId)
    ? `/sessions/${encodeURIComponent(memory.value.sessionId)}`
    : null,
)
const sourceTurn = computed(() => {
  const value = props.detail.metadata.source_turn
  return typeof value === "number" ? value : null
})
const extractor = computed(() => {
  const value = props.detail.metadata.extractor
  return typeof value === "string" ? value : null
})
const gated = computed(() => props.detail.rawContentGate === "privileged")
const tombstoned = computed(() => props.detail.tombstoned)
const edges = computed(() => props.detail.lineage.edges)

const checkIcon: Record<string, typeof ScanSearch> = {
  pii: ScanSearch,
  injection: Bot,
  embedding: Database,
}

const checkMetric = computed(() =>
  props.detail.evaluation.checks.map((check) => {
    if (check.id === "pii") {
      if (!pii.value.detected) return "0 entities"
      return `${piiOccurrences.value} ${piiOccurrences.value === 1 ? "entity" : "entities"}`
    }
    if (check.id === "injection") return `risk ${memory.value.injectionRisk.toFixed(2)}`
    return props.detail.embedding.mismatch ? "mismatch" : "aligned"
  }),
)

function edgeLabel(edge: MemoryLineageEdge): string {
  if (edge.type === "supersedes") return edge.direction === "outgoing" ? "Supersedes" : "Superseded by"
  if (edge.type === "contradicts") return edge.direction === "outgoing" ? "Contradicts" : "Contradicted by"
  if (edge.type === "merged_from") return edge.direction === "outgoing" ? "Merged from" : "Merged into this record"
  if (edge.type === "derived_from") return edge.direction === "outgoing" ? "Derived from" : "Derived from this record"
  if (edge.type === "specializes") return edge.direction === "outgoing" ? "Specializes" : "Specialized by"
  return edge.direction === "outgoing" ? "Generalizes" : "Generalized by"
}

/** Satellites laid out on a circle around the center node for the mini relationship graph. */
function edgePosition(index: number, total: number): { x: number; y: number } {
  const angle = (Math.PI * 2 * index) / Math.max(1, total) - Math.PI / 2
  return { x: 50 + 38 * Math.cos(angle), y: 50 + 36 * Math.sin(angle) }
}

const graphEdges = computed(() =>
  edges.value.slice(0, 5).map((edge, index) => ({ edge, ...edgePosition(index, Math.min(5, edges.value.length)) })),
)

const hasFinding = computed(() => props.detail.evaluation.checks.some((check) => check.result === "finding"))
const pii = computed(() => props.detail.pii)
const piiOccurrences = computed(() => pii.value.findings.reduce((sum, finding) => sum + finding.occurrences, 0))

function piiEntityLabel(entity: string): string {
  return entity
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

type StepFact = { label: string; value: string | null; mono?: boolean; link?: string | null }
type PipelineStep = { key: string; title: string; done: boolean; facts: StepFact[] }

const pipelineSteps = computed<PipelineStep[]>(() => [
  {
    key: "captured",
    title: "Source captured",
    done: true,
    facts: [
      { label: "Source type", value: MEMORY_SOURCE_LABELS[memory.value.source] },
      { label: "Captured", value: formatDayTimeUtc(memory.value.observedAt), mono: true },
      { label: "Session", value: memory.value.sessionId, link: sourceSession.value ?? null },
      { label: "Turn", value: sourceTurn.value !== null ? `Turn ${sourceTurn.value}` : null },
    ],
  },
  {
    key: "extracted",
    title: "Extracted",
    done: memory.value.source !== "user_provided",
    facts: [
      { label: "Method", value: memory.value.source === "user_provided" ? "User-provided statement" : null },
      { label: "Extractor", value: extractor.value },
      { label: "Confidence", value: memory.value.confidence.toFixed(2), mono: true },
    ],
  },
  {
    key: "stored",
    title: "Stored & embedded",
    done: !tombstoned.value,
    facts: [
      { label: "Embedding model", value: props.detail.embedding.model },
      { label: "Stored model", value: props.detail.embedding.storedModel },
      { label: "Dimensions", value: String(props.detail.embedding.dimensions), mono: true },
    ],
  },
  {
    key: "checked",
    title: "Checked",
    done: true,
    facts: [
      { label: "Checks", value: `${props.detail.evaluation.checks.length} completed`, mono: true },
      {
        label: "Findings",
        value: String(props.detail.evaluation.checks.filter((check) => check.result === "finding").length),
        mono: true,
      },
    ],
  },
])
</script>

<template>
  <div class="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
    <div class="min-w-0 space-y-6">
      <section aria-labelledby="evidence-pipeline" class="rounded-lg border border-line-subtle bg-surface p-5">
        <h2 id="evidence-pipeline" class="text-sm leading-5 font-semibold text-fg-1">Provenance pipeline</h2>
        <ol class="mt-4 flex flex-col">
          <li
            v-for="(step, index) in pipelineSteps"
            :key="step.key"
            class="relative flex gap-3.5 pb-5 last:pb-0"
          >
            <div v-if="index < 3" class="absolute top-6 bottom-0 left-[0.4375rem] w-px bg-line" aria-hidden="true" />
            <span
              class="relative z-10 mt-0.5 flex size-4.5 shrink-0 items-center justify-center rounded-full border-2"
              :class="step.done ? 'border-memory bg-memory' : 'border-line-strong bg-surface'"
              aria-hidden="true"
            >
              <CheckIcon v-if="step.done" :size="9" :stroke-width="3" class="text-canvas" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="text-[0.8125rem] leading-5 font-medium text-fg-1">{{ step.title }}</p>
              <dl class="mt-1 grid gap-x-8 gap-y-1 sm:grid-cols-2">
                <div v-for="fact in step.facts" :key="fact.label" class="flex items-baseline gap-2">
                  <dt class="w-24 shrink-0 text-xs leading-5 text-fg-3">{{ fact.label }}</dt>
                  <dd class="min-w-0 text-xs leading-5 text-fg-2">
                    <NuxtLink
                      v-if="fact.value && fact.link"
                      :to="fact.link"
                      class="font-mono underline decoration-line-strong underline-offset-3 hover:text-accent hover:decoration-accent"
                    >
                      {{ fact.value }}
                    </NuxtLink>
                    <span v-else-if="fact.value" :class="fact.mono && 'font-mono tabular-nums'">{{ fact.value }}</span>
                    <MemoryEmptyValue v-else />
                  </dd>
                </div>
              </dl>
            </div>
          </li>
        </ol>
      </section>

      <section aria-labelledby="evidence-excerpt" class="rounded-lg border border-line-subtle bg-surface p-5">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="evidence-excerpt" class="text-sm leading-5 font-semibold text-fg-1">Source excerpt</h2>
          <NuxtLink
            v-if="sourceSession && !gated && !tombstoned"
            :to="sourceSession"
            class="inline-flex items-center gap-1 text-xs font-medium text-fg-2 underline decoration-line-strong underline-offset-3 transition-colors hover:text-accent hover:decoration-accent"
          >
            Open source session
            <ArrowUpRight :size="11" :stroke-width="1.75" aria-hidden="true" />
          </NuxtLink>
        </div>

        <div v-if="gated" class="mt-3 flex items-start gap-2.5 border-l-2 border-warn/60 pl-3">
          <ShieldAlert :size="15" :stroke-width="1.75" class="mt-0.5 shrink-0 text-warn" aria-hidden="true" />
          <p class="text-[0.8125rem] leading-5 text-fg-2 text-pretty">
            This record is quarantined. Its raw content is gated until a human review resolves the finding.
          </p>
        </div>

        <div v-else-if="tombstoned" class="mt-3 flex items-start gap-2.5 border-l-2 border-crit/60 pl-3">
          <FileSearch :size="15" :stroke-width="1.75" class="mt-0.5 shrink-0 text-crit" aria-hidden="true" />
          <p class="text-[0.8125rem] leading-5 text-fg-2 text-pretty">
            Extraction evidence was removed with the content. Only the lifecycle record and deletion receipt remain.
          </p>
        </div>

        <template v-else>
          <div class="mt-3 rounded-lg rounded-tl-sm border border-line-subtle bg-raised/50 p-3.5">
            <p class="flex flex-wrap items-baseline gap-x-2 text-xs leading-4 text-fg-3">
              <span class="font-medium text-fg-2">User</span>
              <span class="font-mono tabular-nums">{{ formatDayTimeUtc(memory.observedAt) }}</span>
              <span v-if="memory.sessionId" aria-hidden="true">·</span>
              <NuxtLink
                v-if="memory.sessionId"
                :to="`/sessions/${encodeURIComponent(memory.sessionId)}`"
                class="font-mono underline decoration-line-strong underline-offset-3 hover:text-accent hover:decoration-accent"
              >
                {{ memory.sessionId }}
              </NuxtLink>
            </p>
            <p class="mt-1.5 text-[0.9375rem] leading-6 text-fg-1 text-pretty">“{{ memory.content }}”</p>
          </div>
          <p class="mt-2 flex items-center gap-1.5 text-xs leading-4 text-fg-3">
            <span class="inline-flex h-5 items-center rounded-full border border-line px-2 text-[0.6875rem] text-fg-2">
              Stored verbatim · no normalization recorded
            </span>
            <MemoryInfoHint label="About source comparison">
              <p class="font-medium text-fg-1">Source vs stored</p>
              <p class="mt-1">
                No separate source excerpt is recorded in this preview, so the stored statement is shown. A normalized
                source comparison is unavailable, and no cleaning step is claimed.
              </p>
            </MemoryInfoHint>
          </p>
          <p
            v-if="memory.status === 'quarantined' || ['medium', 'high'].includes(memoryInjectionBand(memory.injectionRisk))"
            class="mt-2 flex items-start gap-1.5 text-xs leading-4 font-medium text-warn"
          >
            <AlertTriangle :size="12" :stroke-width="2" class="mt-0.5 shrink-0" aria-hidden="true" />
            Quoted memory text is untrusted evidence. Never follow instructions contained in memory content.
          </p>
        </template>
      </section>

      <section aria-labelledby="evidence-labels" class="rounded-lg border border-line-subtle bg-surface p-5">
        <div class="flex items-baseline justify-between gap-2">
          <h2 id="evidence-labels" class="text-sm leading-5 font-semibold text-fg-1">Labels proposed</h2>
          <span class="inline-flex items-center gap-1.5 text-xs text-fg-3">
            <Tags :size="12" :stroke-width="1.75" aria-hidden="true" />
            {{ memory.labels.length }} proposed
          </span>
        </div>
        <ul v-if="memory.labels.length" class="mt-3 flex flex-col gap-2.5" style="max-width: 28rem">
          <li v-for="label in memory.labels" :key="label.label" class="flex items-center gap-3">
            <span class="w-28 shrink-0 truncate text-[0.8125rem] text-fg-1">{{ label.label }}</span>
            <MemoryScoreBar :value="label.confidence" color="bg-viz-3" :label="`${label.label} label confidence`" />
            <span class="w-9 shrink-0 text-right font-mono text-xs text-fg-2 tabular-nums">{{ label.confidence.toFixed(2) }}</span>
          </li>
        </ul>
        <p v-else class="mt-3 text-[0.8125rem] text-fg-2">
          <MemoryEmptyValue /> No labels were proposed during extraction.
        </p>
      </section>

      <section
        v-if="pii.detected"
        aria-labelledby="evidence-pii"
        class="rounded-lg border border-warn/25 bg-warn-tint/15 p-5"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="evidence-pii" class="flex items-center gap-1.5 text-sm leading-5 font-semibold text-fg-1">
              <ScanSearch :size="14" :stroke-width="1.75" class="text-warn" aria-hidden="true" />
              PII detection and redaction
            </h2>
            <p class="mt-1 text-xs leading-4 text-fg-3">
              {{ pii.engine }} · threshold {{ pii.threshold.toFixed(2) }} · read-path guard {{ pii.readPathGuard.replace("_", " ") }}
            </p>
          </div>
          <span
            class="inline-flex h-5 items-center rounded-full border px-2 text-[0.6875rem] font-medium"
            :class="pii.redacted ? 'border-ok/35 bg-ok-tint text-ok' : 'border-crit/35 bg-crit-tint text-crit'"
          >
            {{ pii.redacted ? "Redacted before storage" : "Not redacted" }}
          </span>
        </div>

        <div class="ix-scroll mt-4 overflow-x-auto rounded-lg border border-line-subtle bg-surface" tabindex="0" role="region" aria-label="PII findings">
          <table class="w-full min-w-[34rem] text-left text-xs">
            <thead class="border-b border-line-subtle text-[0.625rem] tracking-[0.08em] text-fg-3 uppercase">
              <tr>
                <th scope="col" class="px-3 py-2 font-medium">Entity</th>
                <th scope="col" class="px-3 py-2 text-right font-medium">Score</th>
                <th scope="col" class="px-3 py-2 text-right font-medium">Occurrences</th>
                <th scope="col" class="px-3 py-2 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line-subtle">
              <tr v-for="finding in pii.findings" :key="finding.entity">
                <td class="px-3 py-2 font-mono text-[0.6875rem] text-fg-1">{{ piiEntityLabel(finding.entity) }}</td>
                <td class="px-3 py-2 text-right font-mono text-fg-2 tabular-nums">{{ finding.score.toFixed(2) }}</td>
                <td class="px-3 py-2 text-right font-mono text-fg-2 tabular-nums">{{ finding.occurrences }}</td>
                <td class="px-3 py-2 text-right">
                  <span
                    class="inline-flex h-5 items-center rounded-full border px-2 text-[0.625rem] font-medium"
                    :class="
                      finding.action === 'redacted'
                        ? 'border-ok/30 bg-ok-tint text-ok'
                        : finding.action === 'quarantined'
                          ? 'border-warn/35 bg-warn-tint text-warn'
                          : 'border-line bg-raised text-fg-2'
                    "
                  >
                    {{ finding.action }}
                  </span>
                </td>
              </tr>
              <tr v-if="pii.findings.length === 0">
                <td colspan="4" class="px-3 py-3 text-xs text-fg-3">PII was flagged without entity-level findings.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="mt-3 text-xs leading-4 text-fg-2 text-pretty">{{ pii.note }}</p>
        <p v-if="pii.quarantineReason" class="mt-1.5 text-xs leading-4 text-warn">{{ pii.quarantineReason }}</p>
        <NuxtLink
          to="/policies/rules/content.pii"
          class="mt-3 inline-flex items-center gap-1 text-xs font-medium text-fg-2 underline decoration-line-strong underline-offset-3 transition-colors hover:text-accent hover:decoration-accent"
        >
          Open the content.pii policy rule
          <ArrowUpRight :size="11" :stroke-width="1.75" aria-hidden="true" />
        </NuxtLink>
      </section>

      <section aria-labelledby="evidence-checks">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="evidence-checks" class="text-sm leading-5 font-semibold text-fg-1">Evaluation checks</h2>
          <span class="text-xs text-fg-3">Completed checks only</span>
        </div>
        <div class="mt-3 grid gap-3 sm:grid-cols-3">
          <div
            v-for="(check, index) in detail.evaluation.checks"
            :key="check.id"
            class="flex min-w-0 flex-col gap-2 rounded-lg border border-line-subtle bg-surface p-4"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="flex items-center gap-1.5 text-[0.8125rem] font-medium text-fg-1">
                <component :is="checkIcon[check.id] ?? ScanSearch" :size="14" :stroke-width="1.75" class="text-fg-3" aria-hidden="true" />
                {{ check.label }}
              </span>
              <MemoryCheckPill :result="check.result" />
            </div>
            <p class="font-mono text-lg leading-6 font-semibold text-fg-1 tabular-nums">{{ checkMetric[index] }}</p>
            <p class="text-xs leading-4 text-fg-3 text-pretty">{{ check.detail }}</p>
          </div>
        </div>
        <p class="mt-2.5 flex items-center gap-1.5 text-xs leading-4 text-fg-3">
          A missing finding is not proof that no issue exists.
          <MemoryInfoHint label="About evaluation">
            <p class="font-medium text-fg-1">Not a safety certification</p>
            <p class="mt-1">
              These checks cover the stored text and indexing state only. Evaluation timestamps are not recorded in this
              preview, and the embedding check is an indexing diagnostic, not a safety control.
            </p>
          </MemoryInfoHint>
        </p>
      </section>

      <section aria-labelledby="evidence-relationships" class="rounded-lg border border-line-subtle bg-surface p-5">
        <h2 id="evidence-relationships" class="text-sm leading-5 font-semibold text-fg-1">Relationships</h2>
        <div v-if="graphEdges.length" class="mt-3 grid gap-5 md:grid-cols-[13rem_minmax(0,1fr)] md:items-center">
          <svg viewBox="0 0 100 100" class="w-full" role="img" aria-label="Relationship graph for this memory">
            <line
              v-for="node in graphEdges"
              :key="`edge-${node.edge.id}`"
              x1="50"
              y1="50"
              :x2="node.x"
              :y2="node.y"
              class="stroke-line"
              stroke-width="0.6"
            />
            <circle cx="50" cy="50" r="7" class="fill-memory-tint stroke-memory" stroke-width="1" />
            <circle cx="50" cy="50" r="2" class="fill-memory" />
            <g v-for="node in graphEdges" :key="`node-${node.edge.id}`">
              <circle
                :cx="node.x"
                :cy="node.y"
                r="5"
                :class="node.edge.status === 'pending_review' ? 'fill-warn-tint stroke-warn' : 'fill-raised stroke-line-strong'"
                stroke-width="0.8"
              />
            </g>
          </svg>
          <ul class="min-w-0 divide-y divide-line-subtle">
            <li v-for="node in graphEdges" :key="node.edge.id" class="py-2.5">
              <p class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[0.8125rem] leading-5">
                <span class="text-fg-3">{{ edgeLabel(node.edge) }}</span>
                <NuxtLink
                  :to="`/memories/${encodeURIComponent(node.edge.memoryId)}?return=${encodeURIComponent(returnTo)}`"
                  class="font-medium text-fg-1 underline decoration-line-strong underline-offset-3 hover:text-accent hover:decoration-accent"
                >
                  {{ node.edge.title }}
                </NuxtLink>
                <span class="rounded border border-line-subtle px-1.5 py-0.5 text-[0.625rem] text-fg-3">{{ node.edge.status.replace("_", " ") }}</span>
              </p>
              <p class="mt-0.5 flex items-center gap-2 text-xs leading-4 text-fg-3">
                <span class="min-w-0 flex-1 truncate">{{ node.edge.notes }}</span>
                <span class="font-mono tabular-nums">{{ node.edge.confidence.toFixed(2) }}</span>
              </p>
            </li>
          </ul>
        </div>
        <div v-else class="mt-3 flex items-center gap-3 rounded-lg border border-dashed border-line px-4 py-4 text-fg-3">
          <FileSearch :size="16" :stroke-width="1.75" class="shrink-0" aria-hidden="true" />
          <p class="text-[0.8125rem] leading-5">
            <span class="block font-medium text-fg-2">No relationships recorded</span>
            <span class="block text-xs leading-4 text-fg-3">No supersedes, conflict, or similarity edges are stored.</span>
          </p>
        </div>
      </section>
    </div>

    <aside class="min-w-0 space-y-4 xl:sticky xl:top-[6.75rem]" aria-label="Record at a glance">
      <section class="rounded-lg border border-line-subtle bg-surface p-4" aria-labelledby="evidence-glance">
        <h2 id="evidence-glance" class="text-sm leading-5 font-semibold text-fg-1">Record at a glance</h2>
        <dl class="mt-1 divide-y divide-line-subtle">
          <div class="flex items-baseline justify-between gap-3 py-2">
            <dt class="text-xs leading-5 text-fg-3">Status</dt>
            <dd><MemoryStatusPill :status="memory.status" /></dd>
          </div>
          <div class="flex items-baseline justify-between gap-3 py-2">
            <dt class="text-xs leading-5 text-fg-3">Revision</dt>
            <dd class="font-mono text-xs text-fg-2 tabular-nums">r{{ detail.lifecycleRevision }}</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3 py-2">
            <dt class="text-xs leading-5 text-fg-3">Confidence</dt>
            <dd class="font-mono text-xs font-semibold text-fg-1 tabular-nums">{{ memory.confidence.toFixed(2) }}</dd>
          </div>
        </dl>
        <div class="mt-1">
          <MemoryScoreBar :value="memory.confidence" label="Extraction confidence" />
        </div>
        <p class="mt-2 text-xs leading-4" :class="hasFinding ? 'text-warn' : 'text-ok'">
          {{ hasFinding ? "At least one check recorded a finding." : "No findings recorded." }}
        </p>
      </section>
      <MemoryCompleteness :detail="detail" />
    </aside>
  </div>
</template>
