<script setup lang="ts">
import { computed } from "vue"
import { ArrowRight, ArrowUpRight, ShieldCheck } from "@lucide/vue"
import { hasMemoryPreview } from "@/lib/memory-detail-preview"
import { memoryDetailHref } from "@/lib/memory-list-query"
import type { SessionMemory, SessionRound } from "@/lib/session-preview"
import MemoryOutcomePill from "@/components/console/memory/primitives/MemoryOutcomePill.vue"
import MemoryScoreBar from "@/components/console/memory/primitives/MemoryScoreBar.vue"
import SessionRawRecord from "../primitives/SessionRawRecord.vue"
import SessionSectionLabel from "../primitives/SessionSectionLabel.vue"

const props = defineProps<{
  round: SessionRound
  returnTo: string
}>()

const emit = defineEmits<{
  navigate: [panel: "trace"]
  transcript: []
}>()

const retrievalSpan = computed(() => props.round.spans.find((span) => span.label === "memory.retrieve") ?? null)

const ranked = computed(() =>
  props.round.memories
    .map((memory) => ({ memory, rank: 0 }))
    .sort((first, second) => second.memory.similarity - first.memory.similarity)
    .map((entry, index) => ({ ...entry, rank: index + 1 })),
)

const included = computed(() => ranked.value.filter((entry) => entry.memory.usedInResponse))
const unused = computed(() => ranked.value.filter((entry) => !entry.memory.usedInResponse))

const retrievalLine = computed(() => {
  const input = (retrievalSpan.value?.attributes.input ?? {}) as Record<string, unknown>
  const parts: string[] = []
  if (typeof input.query === "string" && input.query) parts.push(`Query “${input.query}”`)
  if (typeof input.limit === "number") parts.push(`top ${input.limit}`)
  if (retrievalSpan.value) parts.push(`${retrievalSpan.value.durationMs} ms`)
  return parts.join(" · ")
})

function ageLabel(memory: SessionMemory): string {
  const match = memory.retrievedAt.match(/^(\d+)([mhd])\s+ago$/)
  if (!match) return memory.retrievedAt
  const value = Number(match[1])
  const unit = match[2] === "m" ? "min" : match[2] === "h" ? "hour" : "day"
  return `created ${value} ${unit}${value === 1 ? "" : "s"} before this turn`
}

function selectSpan(): void {
  emit("navigate", "trace")
}
</script>

<template>
  <div class="space-y-5">
    <div v-if="retrievalLine || retrievalSpan" class="space-y-1.5">
      <p class="text-xs leading-4 text-fg-3">{{ retrievalLine }}</p>
      <button v-if="retrievalSpan" type="button" class="ix-inline-link" @click="selectSpan">
        Show in trace
        <ArrowRight :size="11" :stroke-width="1.75" aria-hidden="true" />
      </button>
    </div>

    <template v-if="round.memories.length === 0">
      <div class="rounded-lg border border-dashed border-line px-3 py-4">
        <p class="text-[0.8125rem] leading-5 text-fg-2">No memories retrieved for this turn.</p>
        <p v-if="retrievalSpan" class="mt-1 text-xs leading-4 text-fg-3">
          Retrieval ran in {{ retrievalSpan.durationMs }} ms; nothing qualified for the context window.
        </p>
      </div>
    </template>

    <template v-else>
      <section v-if="included.length" aria-label="Memories included in the reply">
        <SessionSectionLabel>Included in reply · {{ included.length }}</SessionSectionLabel>
        <div class="mt-1 divide-y divide-line-subtle">
          <article v-for="entry in included" :key="entry.memory.id" class="py-3 first:pt-1.5">
            <div class="flex items-start gap-2">
              <span class="mt-0.5 font-mono text-[0.6875rem] leading-5 text-fg-3 tabular-nums">#{{ entry.rank }}</span>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <NuxtLink
                    v-if="hasMemoryPreview(entry.memory.id)"
                    :to="memoryDetailHref(entry.memory.id, returnTo)"
                    class="min-w-0 text-sm leading-5 font-semibold text-fg-1 underline-offset-4 hover:text-accent-memory hover:underline"
                  >
                    {{ entry.memory.label }}
                  </NuxtLink>
                  <span v-else class="min-w-0 text-sm leading-5 font-semibold text-fg-1">{{ entry.memory.label }}</span>
                  <MemoryOutcomePill usage="injected" labels="reply" class="ml-auto shrink-0" />
                </div>
                <p class="mt-1 text-sm leading-5 text-fg-1 text-pretty">{{ entry.memory.fact }}</p>
                <div class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                  <MemoryScoreBar
                    :value="entry.memory.similarity"
                    size="sm"
                    class="max-w-20"
                    :label="`Similarity ${entry.memory.similarity.toFixed(2)}`"
                  />
                  <span class="font-mono text-[0.6875rem] leading-4 text-fg-2 tabular-nums">{{ entry.memory.similarity.toFixed(2) }}</span>
                  <span class="inline-flex h-5 items-center rounded-full border border-line-subtle bg-raised px-1.5 text-[0.625rem] leading-none text-fg-2">
                    {{ entry.memory.scope }} scope
                  </span>
                  <span class="text-[0.6875rem] leading-4 text-fg-3" :title="`Recorded as ${entry.memory.retrievedAt}`">
                    {{ ageLabel(entry.memory) }}
                  </span>
                </div>
                <SessionSectionLabel class="mt-2.5">Why retrieved</SessionSectionLabel>
                <p class="mt-1 text-[0.8125rem] leading-5 text-fg-2 text-pretty">{{ entry.memory.why }}</p>
                <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <NuxtLink
                    v-if="hasMemoryPreview(entry.memory.id)"
                    :to="memoryDetailHref(entry.memory.id, returnTo)"
                    class="ix-inline-link"
                  >
                    Open memory
                    <ArrowUpRight :size="11" :stroke-width="1.75" aria-hidden="true" />
                  </NuxtLink>
                  <span v-else class="text-[0.6875rem] leading-4 text-fg-3">Detail page unavailable in this preview.</span>
                </div>
                <SessionRawRecord class="mt-2.5" :value="entry.memory" />
              </div>
            </div>
          </article>
        </div>
      </section>

      <section v-if="unused.length" aria-label="Memories retrieved but not used">
        <SessionSectionLabel>Retrieved, not used · {{ unused.length }}</SessionSectionLabel>
        <div class="mt-1 divide-y divide-line-subtle">
          <article v-for="entry in unused" :key="entry.memory.id" class="py-3 first:pt-1.5">
            <div class="flex items-start gap-2">
              <span class="mt-0.5 font-mono text-[0.6875rem] leading-5 text-fg-3 tabular-nums">#{{ entry.rank }}</span>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <NuxtLink
                    v-if="hasMemoryPreview(entry.memory.id)"
                    :to="memoryDetailHref(entry.memory.id, returnTo)"
                    class="min-w-0 text-sm leading-5 font-semibold text-fg-2 underline-offset-4 hover:text-fg-1 hover:underline"
                  >
                    {{ entry.memory.label }}
                  </NuxtLink>
                  <span v-else class="min-w-0 text-sm leading-5 font-semibold text-fg-2">{{ entry.memory.label }}</span>
                  <MemoryOutcomePill usage="retrieved_only" labels="reply" class="ml-auto shrink-0" />
                </div>
                <p class="mt-1 text-sm leading-5 text-fg-3 text-pretty">{{ entry.memory.fact }}</p>
                <div class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                  <MemoryScoreBar
                    :value="entry.memory.similarity"
                    size="sm"
                    color="bg-fg-3"
                    class="max-w-20"
                    :label="`Similarity ${entry.memory.similarity.toFixed(2)}`"
                  />
                  <span class="font-mono text-[0.6875rem] leading-4 text-fg-3 tabular-nums">{{ entry.memory.similarity.toFixed(2) }}</span>
                  <span class="inline-flex h-5 items-center rounded-full border border-line-subtle bg-raised px-1.5 text-[0.625rem] leading-none text-fg-3">
                    {{ entry.memory.scope }} scope
                  </span>
                  <span class="text-[0.6875rem] leading-4 text-fg-3" :title="`Recorded as ${entry.memory.retrievedAt}`">
                    {{ ageLabel(entry.memory) }}
                  </span>
                </div>
                <SessionSectionLabel class="mt-2.5">Why retrieved</SessionSectionLabel>
                <p class="mt-1 text-[0.8125rem] leading-5 text-fg-3 text-pretty">{{ entry.memory.why }}</p>
                <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <NuxtLink
                    v-if="hasMemoryPreview(entry.memory.id)"
                    :to="memoryDetailHref(entry.memory.id, returnTo)"
                    class="ix-inline-link"
                  >
                    Open memory
                    <ArrowUpRight :size="11" :stroke-width="1.75" aria-hidden="true" />
                  </NuxtLink>
                  <span v-else class="text-[0.6875rem] leading-4 text-fg-3">Detail page unavailable in this preview.</span>
                </div>
                <SessionRawRecord class="mt-2.5" :value="entry.memory" />
              </div>
            </div>
          </article>
        </div>
      </section>

      <p class="flex items-start gap-1.5 border-t border-line-subtle pt-3 text-xs leading-4 text-fg-2">
        <ShieldCheck :size="13" :stroke-width="1.75" class="mt-0.5 shrink-0 text-fg-3" aria-hidden="true" />
        <span>Retrieved memories enter context as untrusted data, never as instructions.</span>
      </p>

      <button type="button" class="ix-inline-link" @click="emit('transcript')">
        Show in transcript
        <ArrowRight :size="11" :stroke-width="1.75" aria-hidden="true" />
      </button>
    </template>
  </div>
</template>

<style scoped>
.ix-inline-link {
  display: inline-flex;
  align-items: center;
  gap: 0.1875rem;
  border-radius: 3px;
  font-size: 0.6875rem;
  line-height: 1rem;
  font-weight: 500;
  color: var(--ix-fg-2);
  text-decoration: underline;
  text-decoration-color: var(--ix-line-strong);
  text-underline-offset: 2px;
  transition: color 120ms;
}

.ix-inline-link:hover {
  color: var(--ix-fg-1);
}

.ix-inline-link:focus-visible {
  outline: 2px solid var(--ix-accent-memory);
  outline-offset: 2px;
}
</style>
