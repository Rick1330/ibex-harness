<script setup lang="ts">
import { computed } from "vue"
import { ChevronRight } from "@lucide/vue"
import GovernLifecyclePill from "@/components/console/govern/primitives/GovernLifecyclePill.vue"
import {
  directiveCandidate,
  directiveCheckSummary,
  directiveCheckTarget,
  directiveLive,
  directivePrimaryState,
  type Directive,
} from "@/lib/directive-preview"
import { formatGovernRelative } from "@/lib/govern-format"

const props = defineProps<{
  directive: Directive
}>()

const emit = defineEmits<{ open: []; quick: [] }>()

const live = computed(() => directiveLive(props.directive))
const candidate = computed(() => directiveCandidate(props.directive))
const checks = computed(() => directiveCheckSummary(directiveCheckTarget(props.directive)))
const latest = computed(() => props.directive.versions[0] ?? null)

const checkTone = computed(() =>
  checks.value.tone === "destructive"
    ? "text-crit"
    : checks.value.tone === "warning"
      ? "text-warn"
      : checks.value.tone === "success"
        ? "text-ok"
        : "text-fg-3",
)

</script>

<template>
  <article
    class="rounded-lg border border-line-subtle bg-surface p-3.5 transition-colors hover:border-line"
  >
    <div class="flex items-start justify-between gap-2">
      <div class="min-w-0">
        <h2 class="truncate text-sm font-semibold text-fg-1">{{ directive.name }}</h2>
        <p class="mt-0.5 line-clamp-2 text-xs leading-5 text-fg-3">{{ directive.description }}</p>
      </div>
      <GovernLifecyclePill :state="directivePrimaryState(directive)" />
    </div>

    <dl class="mt-3 grid grid-cols-3 gap-2 border-t border-line-subtle pt-2.5 text-xs">
      <div>
        <dt class="text-[0.6875rem] text-fg-3">Live</dt>
        <dd class="mt-0.5 font-mono text-fg-1 tabular-nums">{{ live?.version ?? "None" }}</dd>
      </div>
      <div>
        <dt class="text-[0.6875rem] text-fg-3">Candidate</dt>
        <dd class="mt-0.5 font-mono text-fg-1 tabular-nums">{{ candidate?.version ?? "None" }}</dd>
      </div>
      <div>
        <dt class="text-[0.6875rem] text-fg-3">Checks</dt>
        <dd class="mt-0.5 font-mono tabular-nums" :class="checkTone">{{ checks.label }}</dd>
      </div>
    </dl>

    <div class="mt-2.5 flex items-center justify-between gap-2 text-[0.6875rem] text-fg-3">
      <span v-if="latest" class="min-w-0 truncate">
        {{ latest.author }} · {{ formatGovernRelative(latest.createdAt) }} · {{ directive.agents.length }} {{ directive.agents.length === 1 ? "agent" : "agents" }}
      </span>
      <div class="flex shrink-0 items-center gap-1">
        <button
          type="button"
          class="rounded px-2 py-1 font-medium text-fg-2 hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
          :aria-label="`Quick look at ${directive.name}`"
          @click="emit('quick')"
        >
          Quick look
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-0.5 rounded px-2 py-1 font-medium text-fg-2 hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
          :aria-label="`Open ${directive.name}`"
          @click="emit('open')"
        >
          Open
          <ChevronRight :size="11" :stroke-width="2" aria-hidden="true" />
        </button>
      </div>
    </div>
  </article>
</template>
