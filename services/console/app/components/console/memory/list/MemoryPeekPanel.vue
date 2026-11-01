<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"
import { ArrowUpRight, CalendarClock, GitBranch, PanelRightClose, ShieldAlert, X } from "@lucide/vue"
import { MEMORY_CATEGORY_LABELS, MEMORY_SOURCE_LABELS, type PreviewMemory } from "@/lib/memory-preview"
import { getMemoryDetail } from "@/lib/memory-detail-preview"
import { memoryDetailHref } from "@/lib/memory-list-query"
import { memoryFlags } from "@/lib/memory-list"
import MemoryAgentBadge from "./primitives/MemoryAgentBadge.vue"
import MemoryCategoryChip from "./primitives/MemoryCategoryChip.vue"
import MemoryFlagPill from "./primitives/MemoryFlagPill.vue"
import MemoryScopeChip from "./primitives/MemoryScopeChip.vue"
import MemorySparkline from "./primitives/MemorySparkline.vue"
import MemoryStatementText from "./primitives/MemoryStatementText.vue"
import MemoryScoreBar from "@/components/console/memory/primitives/MemoryScoreBar.vue"
import MemoryStatusPill from "@/components/console/memory/primitives/MemoryStatusPill.vue"

const props = defineProps<{
  memory: PreviewMemory
  returnTo: string
}>()

const emit = defineEmits<{ close: [] }>()

const panel = ref<HTMLElement | null>(null)
const detail = computed(() => getMemoryDetail(props.memory.id))
const flags = computed(() => memoryFlags(props.memory))
const href = computed(() => memoryDetailHref(props.memory.id, props.returnTo))
const untrusted = computed(() => props.memory.injectionRisk >= 0.5)
const retrieval = computed(() => detail.value?.retrieval)
const lineage = computed(() => detail.value?.lineage)

const edgeClass = computed(() => {
  return "border-l-memory"
})

watch(
  () => props.memory.id,
  async () => {
    await nextTick()
    panel.value?.focus()
  },
  { immediate: true },
)
</script>

<template>
  <aside
    ref="panel"
    class="ix-memory-peek fixed inset-y-0 right-0 z-40 flex w-[min(27.5rem,100vw)] flex-col border-l border-line bg-surface-1 shadow-2xl outline-none"
    :class="edgeClass"
    role="dialog"
    aria-modal="false"
    :aria-label="`Peek at ${memory.id}`"
    tabindex="-1"
    @keydown.esc.stop.prevent="emit('close')"
  >
    <header class="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-line-subtle px-3">
      <div class="flex min-w-0 items-center gap-2">
        <PanelRightClose :size="14" :stroke-width="1.8" class="shrink-0 text-fg-3" aria-hidden="true" />
        <p class="truncate font-mono text-[0.6875rem] text-fg-3">{{ memory.id }}</p>
        <MemoryStatusPill v-if="memory.status !== 'active'" :status="memory.status" compact />
      </div>
      <button
        type="button"
        class="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
        aria-label="Close peek panel"
        @click="emit('close')"
      >
        <X :size="15" :stroke-width="1.8" aria-hidden="true" />
      </button>
    </header>

    <div class="ix-scroll min-h-0 flex-1 overflow-y-auto px-4 py-3">
      <p class="text-sm leading-6 text-fg-1">
        <MemoryStatementText :text="memory.content" :untrusted="untrusted" />
      </p>
      <p v-if="untrusted" class="mt-1.5 flex items-center gap-1 text-[0.6875rem] text-warn">
        <ShieldAlert :size="11" :stroke-width="1.9" aria-hidden="true" />
        Untrusted text. Treated as data, never as instructions.
      </p>

      <div v-if="flags.length" class="mt-2.5 flex flex-wrap items-center gap-1">
        <MemoryFlagPill v-for="flag in flags" :key="flag.kind" :flag="flag" />
      </div>

      <dl class="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 border-t border-line-subtle pt-3 text-xs">
        <div class="min-w-0">
          <dt class="text-[0.6875rem] text-fg-3">Category</dt>
          <dd class="mt-0.5"><MemoryCategoryChip :category="memory.category" variant="chip" /></dd>
        </div>
        <div class="min-w-0">
          <dt class="text-[0.6875rem] text-fg-3">Scope</dt>
          <dd class="mt-0.5"><MemoryScopeChip :visibility="memory.visibility" variant="chip" /></dd>
        </div>
        <div class="col-span-2 min-w-0">
          <dt class="text-[0.6875rem] text-fg-3">Agent</dt>
          <dd class="mt-1"><MemoryAgentBadge :name="memory.agent" :agent-id="memory.agentId" /></dd>
        </div>
        <div class="min-w-0">
          <dt class="text-[0.6875rem] text-fg-3">Source</dt>
          <dd class="mt-0.5 text-fg-2">{{ MEMORY_SOURCE_LABELS[memory.source] }}</dd>
        </div>
        <div class="min-w-0">
          <dt class="text-[0.6875rem] text-fg-3">Primary label</dt>
          <dd class="mt-0.5 text-fg-2">{{ MEMORY_CATEGORY_LABELS[memory.category] }}</dd>
        </div>
      </dl>

      <div class="mt-3 grid grid-cols-2 gap-3 border-t border-line-subtle pt-3">
        <div class="min-w-0">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-[0.6875rem] text-fg-3">Confidence</span>
            <span class="font-mono text-xs text-fg-2 tabular-nums">{{ memory.confidence.toFixed(2) }}</span>
          </div>
          <MemoryScoreBar :value="memory.confidence" size="sm" class="mt-1.5" :label="`Confidence ${memory.confidence.toFixed(2)}`" />
        </div>
        <div class="min-w-0">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-[0.6875rem] text-fg-3">Usefulness</span>
            <span class="font-mono text-xs text-fg-2 tabular-nums">{{ memory.usefulness.toFixed(2) }}</span>
          </div>
          <MemoryScoreBar
            :value="memory.usefulness"
            size="sm"
            color="bg-fg-2"
            class="mt-1.5"
            :label="`Usefulness ${memory.usefulness.toFixed(2)}`"
          />
        </div>
      </div>

      <section class="mt-3 border-t border-line-subtle pt-3" aria-label="Retrieval history">
        <div class="flex items-center justify-between gap-2">
          <h2 class="text-[0.6875rem] font-medium tracking-[0.04em] text-fg-3 uppercase">Retrievals</h2>
          <span class="font-mono text-xs text-fg-2 tabular-nums">{{ memory.retrievalCount }}</span>
        </div>
        <div v-if="retrieval" class="mt-1.5 flex items-end gap-2">
          <MemorySparkline
            :points="retrieval.sparkline"
            :label="`${memory.retrievalCount} retrievals over the last 14 days`"
            :width="120"
            :height="28"
          />
          <span class="text-[0.6875rem] text-fg-3">Last 14 days · last {{ memory.lastRetrievedLabel }}</span>
        </div>
        <p class="mt-1.5 text-[0.6875rem] leading-4 text-fg-3">
          Inclusion is not influence. Retrieval does not measure whether an answer used this memory.
        </p>
      </section>

      <section class="mt-3 border-t border-line-subtle pt-3" aria-label="Lineage">
        <div class="flex items-center justify-between gap-2">
          <h2 class="text-[0.6875rem] font-medium tracking-[0.04em] text-fg-3 uppercase">Lineage</h2>
          <GitBranch :size="11" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
        </div>
        <ul v-if="lineage?.edges.length" class="mt-1.5 space-y-1.5">
          <li v-for="edge in lineage.edges.slice(0, 4)" :key="edge.id" class="min-w-0 text-xs">
            <span class="font-mono text-[0.625rem] text-fg-3">{{ edge.type }}</span>
            <span class="text-fg-2"> · {{ edge.title }}</span>
            <span v-if="edge.status !== 'active'" class="ml-1 text-[0.6875rem] text-warn">{{ edge.status }}</span>
          </li>
        </ul>
        <p v-else class="mt-1.5 text-[0.6875rem] leading-4 text-fg-3">
          No lineage edge is recorded for this memory.
        </p>
      </section>

      <section class="mt-3 border-t border-line-subtle pt-3" aria-label="Validity">
        <div class="flex items-center gap-1.5">
          <CalendarClock :size="11" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
          <h2 class="text-[0.6875rem] font-medium tracking-[0.04em] text-fg-3 uppercase">Validity</h2>
        </div>
        <p class="mt-1 text-xs text-fg-2">
          <template v-if="memory.validUntil">
            Expires {{ memory.validUntil.replace("T", " ").replace("Z", " UTC") }}
            <span :class="memory.validity === 'expired' ? 'text-crit' : 'text-warn'"> · {{ memory.validityLabel }}</span>
          </template>
          <template v-else>No expiry is recorded. Open validity is not an endorsement.</template>
        </p>
      </section>
    </div>

    <footer class="flex shrink-0 items-center justify-between gap-2 border-t border-line-subtle p-3">
      <span class="text-[0.6875rem] text-fg-3">Read-only peek</span>
      <NuxtLink
        :to="href"
        class="inline-flex h-8 items-center gap-1.5 rounded-md bg-memory px-3 text-xs font-semibold text-canvas transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
      >
        Open full view
        <ArrowUpRight :size="13" :stroke-width="2" aria-hidden="true" />
      </NuxtLink>
    </footer>
  </aside>
</template>

<style scoped>
.ix-memory-peek {
  animation: ix-peek-in 160ms ease-out;
}
@keyframes ix-peek-in {
  from {
    transform: translateX(1.5rem);
    opacity: 0;
  }
  to {
    transform: none;
    opacity: 1;
  }
}
</style>
