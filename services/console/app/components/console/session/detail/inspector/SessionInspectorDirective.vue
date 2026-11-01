<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import { ArrowRight, Check, Copy, Lock } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { SessionRound } from "@/lib/session-preview"
import MemoryInfoHint from "@/components/console/memory/primitives/MemoryInfoHint.vue"
import SessionCaveat from "../primitives/SessionCaveat.vue"
import SessionKeyValueList from "../primitives/SessionKeyValueList.vue"
import SessionRawRecord from "../primitives/SessionRawRecord.vue"
import SessionSectionLabel from "../primitives/SessionSectionLabel.vue"

const props = defineProps<{
  round: SessionRound
}>()

const emit = defineEmits<{
  span: [label: string]
  copy: [value: string, label: string]
}>()

const copied = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

const directive = computed(() => props.round.directive)
const previous = computed(() => directive.value.versions.find((version) => !version.current) ?? null)

const rows = computed(() => [
  { label: "Resolved for", value: directive.value.resolvedFor, mono: true },
  { label: "Pinned", value: `Before generation · +${directive.value.pinnedAtOffsetMs} ms` },
  { label: "Scope", value: directive.value.scope, mono: true },
])

function copyId(): void {
  emit("copy", directive.value.id, "Directive ID")
  copied.value = true
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    copied.value = false
  }, 1_500)
}

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <div class="space-y-5">
    <div class="flex justify-end">
      <MemoryInfoHint label="What is a directive?">
        A directive is the instruction the agent was given for this turn. Policies, in the next tab, decide which
        actions the agent is allowed to take.
      </MemoryInfoHint>
    </div>

    <section>
      <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span class="inline-flex h-5 items-center rounded border border-line-subtle bg-raised px-1.5 text-[0.625rem] leading-none font-medium tracking-[0.04em] text-fg-2 uppercase">
          Directive
        </span>
        <span class="min-w-0 text-sm leading-5 font-semibold text-fg-1">{{ directive.name }}</span>
        <span class="inline-flex h-5.5 items-center gap-1 rounded-full border border-memory/40 bg-memory-tint px-2 text-xs leading-none font-medium text-memory">
          <span class="font-mono">{{ directive.version }}</span>
          <span class="text-fg-2">pinned</span>
        </span>
      </div>
      <div class="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-xs leading-4 text-fg-3">
        <span class="font-mono">{{ directive.scope }}</span>
        <span aria-hidden="true">·</span>
        <span class="min-w-0 truncate font-mono text-fg-2">{{ directive.id }}</span>
        <button
          type="button"
          class="inline-flex size-5 items-center justify-center rounded text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          :aria-label="copied ? 'Directive ID copied' : `Copy directive ID ${directive.id}`"
          @click="copyId"
        >
          <Check v-if="copied" :size="11" :stroke-width="2" class="text-ok" aria-hidden="true" />
          <Copy v-else :size="11" :stroke-width="1.75" aria-hidden="true" />
        </button>
        <span aria-hidden="true">·</span>
        <span>published {{ directive.publishedAt }}</span>
      </div>
    </section>

    <blockquote class="ix-directive-text">{{ directive.excerpt }}</blockquote>

    <section>
      <SessionSectionLabel>Resolution</SessionSectionLabel>
      <SessionKeyValueList class="mt-1" :rows="rows" />
      <p class="mt-2 text-[0.8125rem] leading-5 text-fg-3 text-pretty">{{ directive.whyApplied }}</p>
    </section>

    <section>
      <SessionSectionLabel>Versions</SessionSectionLabel>
      <ol class="ix-versions mt-2" aria-label="Directive versions">
        <li v-for="version in directive.versions" :key="version.version" class="ix-version">
          <span class="ix-version-node" :class="version.current && 'ix-version-node-current'" aria-hidden="true" />
          <span class="min-w-0">
            <NuxtLink
              v-if="!version.current && version.href"
              :to="version.href"
              class="font-mono text-xs text-fg-2 underline-offset-4 hover:text-fg-1 hover:underline"
            >
              {{ version.version }}
            </NuxtLink>
            <span v-else class="font-mono text-xs" :class="version.current ? 'text-fg-1' : 'text-fg-2'">{{ version.version }}</span>
            <span class="ml-1 text-[0.6875rem] leading-4 text-fg-3">{{ version.date }}</span>
            <span v-if="version.current" class="ml-1 text-[0.6875rem] leading-4 text-fg-3">· pinned to this turn</span>
          </span>
        </li>
      </ol>

      <p class="mt-3 text-[0.8125rem] leading-5 text-fg-2 text-pretty">
        <span class="font-medium text-fg-1">What changed in {{ directive.version }}.</span>
        {{ directive.change }}
      </p>

      <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <Tooltip :delay-duration="120">
          <TooltipTrigger as-child>
            <button
              type="button"
              class="ix-disabled-button"
              disabled
              aria-disabled="true"
            >
              <Lock :size="11" :stroke-width="1.75" aria-hidden="true" />
              Compare with {{ previous?.version ?? "previous version" }}
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" :side-offset="6" class="!text-xs">Comparison isn't available in this preview.</TooltipContent>
        </Tooltip>
        <button type="button" class="ix-inline-link" @click="emit('span', 'context.assemble')">
          Show in trace
          <ArrowRight :size="11" :stroke-width="1.75" aria-hidden="true" />
        </button>
      </div>
    </section>

    <SessionCaveat
      summary="The version summary records what changed."
      detail="It does not prove which clause influenced the response."
    />

    <SessionRawRecord :value="directive" />
  </div>
</template>

<style scoped>
.ix-directive-text {
  border: 1px solid var(--ix-line-subtle);
  border-left: 3px solid var(--ix-line-strong);
  border-radius: 10px;
  background: var(--ix-surface);
  padding: 0.875rem 1rem;
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--ix-fg-1);
  text-wrap: pretty;
}

.ix-versions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0;
}

.ix-version {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.75rem 0.25rem 0;
}

.ix-version:not(:last-child)::after {
  content: "";
  width: 1rem;
  height: 1px;
  margin-left: 0.125rem;
  background: var(--ix-line);
}

.ix-version-node {
  display: inline-block;
  width: 0.5rem;
  height: 0.5rem;
  flex: none;
  border: 1.5px solid var(--ix-line-strong);
  border-radius: 9999px;
  background: var(--ix-surface);
}

.ix-version-node-current {
  border-color: var(--ix-memory);
  background: var(--ix-memory);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ix-memory) 18%, transparent);
}

.ix-disabled-button {
  display: inline-flex;
  height: 1.75rem;
  cursor: not-allowed;
  align-items: center;
  gap: 0.3125rem;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 6px;
  background: transparent;
  padding: 0 0.5rem;
  font-size: 0.6875rem;
  line-height: 1;
  color: var(--ix-fg-3);
  opacity: 0.75;
}

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
