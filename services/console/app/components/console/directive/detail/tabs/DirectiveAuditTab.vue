<script setup lang="ts">
import { computed } from "vue"
import { ExternalLink } from "@lucide/vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import GovernVersionTag from "@/components/console/govern/primitives/GovernVersionTag.vue"
import {
  DIRECTIVE_EVENT_LABELS,
  directiveAuditEvents,
  directiveEventHref,
  type Directive,
  type DirectiveEventAction,
} from "@/lib/directive-preview"
import { formatGovernDate, formatGovernStamp } from "@/lib/govern-format"

const props = defineProps<{ directive: Directive }>()

const events = computed(() => directiveAuditEvents(props.directive))

const groups = computed(() => {
  const map = new Map<string, typeof events.value>()
  for (const event of events.value) {
    const day = formatGovernDate(event.at)
    const bucket = map.get(day) ?? []
    bucket.push(event)
    map.set(day, bucket)
  }
  return [...map.entries()]
})

const actionTone: Record<DirectiveEventAction, string> = {
  created: "text-fg-2",
  submitted: "text-fg-2",
  check_passed: "text-ok",
  check_failed: "text-crit",
  approved: "text-ok",
  changes_requested: "text-warn",
  promoted: "text-ok",
  rolled_back: "text-warn",
  rejected: "text-crit",
}
</script>

<template>
  <div class="min-w-0 space-y-4">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <p class="text-xs leading-5 text-fg-3">
        Every directive action is append-only. Each row carries the event ID used by the audit ledger.
      </p>
      <span class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ events.length }} events</span>
    </div>

    <section v-for="[day, dayEvents] in groups" :key="day" class="min-w-0" :aria-label="`Events on ${day}`">
      <h2 class="mb-1.5 text-[0.6875rem] font-medium tracking-[0.06em] text-fg-3 uppercase">{{ day }}</h2>
      <ol class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
        <li v-for="event in dayEvents" :key="event.id" class="flex flex-col gap-2 border-b border-line-subtle px-4 py-3 last:border-b-0 sm:flex-row sm:items-start">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span class="text-xs font-medium" :class="actionTone[event.action]">{{ DIRECTIVE_EVENT_LABELS[event.action] }}</span>
              <GovernVersionTag label="Version" :value="event.version" tone="muted" />
              <span class="text-[0.6875rem] text-fg-3">by <span class="text-fg-2">{{ event.actor }}</span></span>
              <span class="font-mono text-[0.625rem] text-fg-3" :title="formatGovernStamp(event.at)">{{ formatGovernStamp(event.at) }}</span>
            </div>
            <p class="mt-1 text-xs leading-5 text-fg-2">{{ event.summary }}</p>
            <div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
              <GovernCopyId :id="event.id" label="Event" truncate />
              <span class="font-mono text-[0.625rem] text-fg-3">{{ event.evidenceId === event.id ? "evidence recorded" : `evidence ${event.evidenceId}` }}</span>
            </div>
          </div>
          <NuxtLink
            :to="directiveEventHref(event)"
            class="inline-flex shrink-0 items-center gap-1 rounded text-[0.6875rem] text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            :aria-label="`Open audit evidence for ${DIRECTIVE_EVENT_LABELS[event.action]} on ${event.version}`"
          >
            Open evidence
            <ExternalLink :size="11" :stroke-width="1.9" aria-hidden="true" />
          </NuxtLink>
        </li>
      </ol>
    </section>
  </div>
</template>
