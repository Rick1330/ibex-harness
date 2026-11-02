<script setup lang="ts">
import { computed } from "vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import MemoryStatusPill from "./LiveMemoryStatusPill.vue"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import type { PublicOperatorMemory } from "~~/shared/operator/public"

const props = defineProps<{ memory: PublicOperatorMemory; returnTo: string }>()

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
    </section>
  </div>
</template>
