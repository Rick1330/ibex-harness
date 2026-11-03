<script setup lang="ts">
import { computed } from "vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import MemoryStatusPill from "./LiveMemoryStatusPill.vue"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import type { PublicOperatorMemoryDetail } from "~~/shared/operator/public"
import type { OperatorMemoryLineageEdge, OperatorMemoryLineageTarget } from "~~/shared/operator/contracts"

const props = defineProps<{ memory: PublicOperatorMemoryDetail; returnTo: string }>()

const RELATIONSHIP_LABELS: Record<OperatorMemoryLineageEdge["relationship_type"], string> = {
  supersedes: "Supersedes",
  contradicts: "Contradicts",
  specializes: "Specializes",
  generalizes: "Generalizes",
  merged_from: "Merged from",
  derived_from: "Derived from",
}

const lineage = computed(() => props.memory.lineage)
const hasLineage = computed(
  () =>
    lineage.value.superseded_by !== null ||
    lineage.value.merged_into !== null ||
    lineage.value.replaces.length > 0 ||
    lineage.value.replaced_by.length > 0,
)

function memoryHref(memoryId: string): string {
  return `/memories/${encodeURIComponent(memoryId)}?return=${encodeURIComponent(props.returnTo)}`
}

/**
 * A target is linkable only while it is a live-visible record.
 *
 * The detail route serves retained rows, so a tombstoned or deleted target would
 * resolve — but linking to it would read as a live successor, which it is not.
 */
function isLinkable(target: { status: string, tombstoned: boolean } | null | undefined): boolean {
  return Boolean(target) && !target!.tombstoned && target!.status !== "deleted"
}

function targetState(target: OperatorMemoryLineageTarget): string {
  return target.tombstoned ? `${target.status} · tombstoned` : target.status
}

function edgeState(edge: OperatorMemoryLineageEdge): string {
  if (edge.tombstoned) return `${edge.status} · tombstoned`
  return edge.status
}

const shortId = computed(() => `${props.memory.id.slice(0, 8)}…${props.memory.id.slice(-4)}`)

function piiLabel(): string {
  if (!props.memory.pii_detected) return "None detected"
  return props.memory.pii_redacted ? "Detected and redacted" : "Detected, not redacted"
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-5">
    <ConsolePageHeader
      :title="`Memory ${shortId}`"
      definition="Metadata, lifecycle, provenance, and validity for one memory record."
      state="live"
      :verdict="`Status: ${memory.status}`"
      contract="operator.memories.v1"
      scope="Organization"
      range="Memory record"
      :observed="memory.updated_at"
      caveat="Content, embeddings, and free-form metadata are not part of this contract and are not shown."
    >
      <template #back>
        <NuxtLink :to="returnTo" class="mb-2 inline-flex text-xs text-fg-3 hover:text-fg-1">
          ← Back to memories
        </NuxtLink>
      </template>
      <template #actions>
        <MemoryStatusPill :status="memory.status" />
      </template>
    </ConsolePageHeader>

    <section class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Memory counters">
      <GovernStatTile
        label="Content tokens"
        :value="formatGovernNumber(memory.content_tokens)"
        helper="Token count only; content is not exposed"
      />
      <GovernStatTile
        label="Retrievals"
        :value="formatGovernNumber(memory.retrieval_count)"
        :helper="`Last ${formatGovernStamp(memory.last_retrieved_at)}`"
      />
      <GovernStatTile
        label="Lifecycle revision"
        :value="String(memory.lifecycle_revision)"
        :helper="memory.tombstoned ? 'Tombstoned' : 'Not tombstoned'"
      />
      <GovernStatTile
        label="PII"
        :value="memory.pii_detected ? 'Detected' : 'None'"
        :helper="piiLabel()"
        :tone="memory.pii_detected && !memory.pii_redacted ? 'warning' : 'default'"
      />
    </section>

    <section class="grid grid-cols-1 gap-4 lg:grid-cols-3" aria-label="Memory metadata">
      <div class="rounded-lg border border-line-subtle bg-surface p-4 lg:col-span-2">
        <h2 class="ix-heading text-fg-1">Identity and classification</h2>
        <dl class="mt-3 grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">
          <div>
            <dt class="ix-label">Memory ID</dt>
            <dd class="mt-0.5 break-all font-mono text-xs text-fg-1">{{ memory.id }}</dd>
          </div>
          <div>
            <dt class="ix-label">Agent ID</dt>
            <dd class="mt-0.5 break-all font-mono text-xs text-fg-1">{{ memory.agent_id }}</dd>
          </div>
          <div>
            <dt class="ix-label">Session ID</dt>
            <dd class="mt-0.5 break-all font-mono text-xs text-fg-1">{{ memory.session_id ?? "Not attached" }}</dd>
          </div>
          <div>
            <dt class="ix-label">Category</dt>
            <dd class="mt-0.5 text-xs text-fg-1">{{ memory.category }}</dd>
          </div>
          <div>
            <dt class="ix-label">Source</dt>
            <dd class="mt-0.5 text-xs text-fg-1">{{ memory.source }}</dd>
          </div>
          <div>
            <dt class="ix-label">Visibility</dt>
            <dd class="mt-0.5 text-xs text-fg-1">{{ memory.visibility }}{{ memory.pinned ? " · pinned" : "" }}</dd>
          </div>
          <div>
            <dt class="ix-label">Confidence</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ memory.confidence.toFixed(2) }}</dd>
          </div>
          <div>
            <dt class="ix-label">Usefulness</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ memory.usefulness_score.toFixed(2) }}</dd>
          </div>
          <div>
            <dt class="ix-label">Created</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernStamp(memory.created_at) }}</dd>
          </div>
          <div>
            <dt class="ix-label">Updated</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernStamp(memory.updated_at) }}</dd>
          </div>
        </dl>
      </div>

      <div class="rounded-lg border border-line-subtle bg-surface p-4">
        <h2 class="ix-heading text-fg-1">Tags</h2>
        <p v-if="memory.tags.length === 0" class="mt-2 text-xs text-fg-3">No tags on this memory.</p>
        <ul v-else class="mt-2 flex flex-wrap gap-1.5" aria-label="Memory tags">
          <li
            v-for="tag in memory.tags"
            :key="tag"
            class="rounded-full border border-line bg-raised px-2 py-0.5 font-mono text-[0.6875rem] text-fg-2"
          >
            {{ tag }}
          </li>
        </ul>
      </div>

      <div class="rounded-lg border border-line-subtle bg-surface p-4 lg:col-span-3">
        <h2 class="ix-heading text-fg-1">Validity and lifecycle</h2>
        <dl class="mt-3 grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt class="ix-label">Valid from</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernStamp(memory.valid_from) }}</dd>
          </div>
          <div>
            <dt class="ix-label">Valid until</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernStamp(memory.valid_until) }}</dd>
          </div>
          <div>
            <dt class="ix-label">Observed at</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernStamp(memory.observed_at) }}</dd>
          </div>
          <div>
            <dt class="ix-label">Expires at</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernStamp(memory.expires_at) }}</dd>
          </div>
        </dl>
      </div>

      <div class="rounded-lg border border-line-subtle bg-surface p-4 lg:col-span-3">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 class="ix-heading text-fg-1">Lineage</h2>
          <p v-if="lineage.edges_truncated" class="text-[0.6875rem] text-fg-3">
            Edge lists are truncated to the 20 most recent links.
          </p>
        </div>

        <p v-if="!hasLineage" class="mt-2 text-xs text-fg-3">
          Nothing superseded or merged into this memory, and it replaced nothing.
        </p>

        <template v-else>
          <dl class="mt-3 grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt class="ix-label">Superseded by</dt>
              <dd class="mt-0.5 text-xs">
                <NuxtLink
                  v-if="lineage.superseded_by && isLinkable(lineage.superseded_by)"
                  :to="memoryHref(lineage.superseded_by.id)"
                  class="font-mono text-fg-1 underline-offset-2 hover:underline"
                >
                  {{ lineage.superseded_by.id.slice(0, 8) }}…
                </NuxtLink>
                <span v-else-if="lineage.superseded_by" class="font-mono text-fg-3">
                  {{ lineage.superseded_by.id.slice(0, 8) }}… · {{ targetState(lineage.superseded_by) }}
                </span>
                <span v-else class="text-fg-3">Not superseded</span>
              </dd>
            </div>
            <div>
              <dt class="ix-label">Merged into</dt>
              <dd class="mt-0.5 text-xs">
                <NuxtLink
                  v-if="lineage.merged_into && isLinkable(lineage.merged_into)"
                  :to="memoryHref(lineage.merged_into.id)"
                  class="font-mono text-fg-1 underline-offset-2 hover:underline"
                >
                  {{ lineage.merged_into.id.slice(0, 8) }}…
                </NuxtLink>
                <span v-else-if="lineage.merged_into" class="font-mono text-fg-3">
                  {{ lineage.merged_into.id.slice(0, 8) }}… · {{ targetState(lineage.merged_into) }}
                </span>
                <span v-else class="text-fg-3">Not merged</span>
              </dd>
            </div>
            <div>
              <dt class="ix-label">Resolved head (up to 5 links)</dt>
              <dd class="mt-0.5 text-xs">
                <NuxtLink
                  v-if="lineage.tip && lineage.tip.id !== memory.id && isLinkable(lineage.tip)"
                  :to="memoryHref(lineage.tip.id)"
                  class="font-mono text-fg-1 underline-offset-2 hover:underline"
                >
                  {{ lineage.tip.id.slice(0, 8) }}…
                </NuxtLink>
                <span
                  v-else-if="lineage.tip && lineage.tip.id !== memory.id"
                  class="font-mono text-fg-3"
                >
                  {{ lineage.tip.id.slice(0, 8) }}… · {{ targetState(lineage.tip) }}
                </span>
                <span v-else class="text-fg-2">This memory</span>
              </dd>
            </div>
          </dl>

          <div v-if="lineage.replaced_by.length" class="mt-4">
            <p class="ix-label">Incoming relationships</p>
            <ul class="mt-1 flex flex-col gap-1 text-xs">
              <li v-for="edge in lineage.replaced_by" :key="edge.memory_id + edge.relationship_type">
                <NuxtLink
                  v-if="isLinkable(edge)"
                  :to="memoryHref(edge.memory_id)"
                  class="font-mono text-fg-1 hover:underline"
                >
                  {{ edge.memory_id.slice(0, 8) }}…
                </NuxtLink>
                <span v-else class="font-mono text-fg-3">{{ edge.memory_id.slice(0, 8) }}…</span>
                <span class="text-fg-3">
                  · {{ RELATIONSHIP_LABELS[edge.relationship_type] }} · confidence
                  {{ edge.confidence.toFixed(2) }} · {{ edgeState(edge) }}
                </span>
              </li>
            </ul>
          </div>

          <div v-if="lineage.replaces.length" class="mt-4">
            <p class="ix-label">Outgoing relationships</p>
            <ul class="mt-1 flex flex-col gap-1 text-xs">
              <li v-for="edge in lineage.replaces" :key="edge.memory_id + edge.relationship_type">
                <NuxtLink
                  v-if="isLinkable(edge)"
                  :to="memoryHref(edge.memory_id)"
                  class="font-mono text-fg-1 hover:underline"
                >
                  {{ edge.memory_id.slice(0, 8) }}…
                </NuxtLink>
                <span v-else class="font-mono text-fg-3">{{ edge.memory_id.slice(0, 8) }}…</span>
                <span class="text-fg-3">
                  · {{ RELATIONSHIP_LABELS[edge.relationship_type] }} · confidence
                  {{ edge.confidence.toFixed(2) }} · {{ edgeState(edge) }}
                </span>
              </li>
            </ul>
          </div>
        </template>

        <p class="mt-3 text-[0.6875rem] leading-4 text-fg-3">
          Lineage is metadata: relationship type, confidence, and the other record's state. The resolved head stops after
          five links, so a longer chain reports its last reachable step rather than the true end. Resolution notes and
          memory content are not part of this contract.
        </p>
      </div>
    </section>
  </div>
</template>
