<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"
import AuditEventView from "@/components/console/audit/detail/AuditEventView.vue"
import { auditEventById } from "@/lib/audit-preview"
import {
  parseAuditEventDetailQuery,
  serializeAuditEventDetailQuery,
  type AuditEventDetailState,
} from "@/lib/govern-query"

const route = useRoute()
const eventId = computed(() => String(route.params.eventId ?? ""))
const event = computed(() => auditEventById(eventId.value))
const state = ref<AuditEventDetailState>(parseAuditEventDetailQuery(route.query))

watch(
  () => route.query,
  () => {
    if (!route.path.startsWith("/audit/events/")) return
    state.value = parseAuditEventDetailQuery(route.query)
  },
)

function update(next: AuditEventDetailState): void {
  state.value = next
  if (!import.meta.client) return
  void navigateTo({ query: Object.fromEntries(serializeAuditEventDetailQuery(next)) }, { replace: true })
}

useHead(() => ({
  title: `${event.value?.id ?? "Event not found"} · Audit log · IBEX Console`,
}))
</script>

<template>
  <AuditEventView v-if="event" :event="event" :state="state" @update="update" />
  <section
    v-else
    class="mx-auto w-full max-w-[90rem] rounded-lg border border-line-subtle bg-surface-1 p-6"
    aria-labelledby="audit-event-not-found"
  >
    <NuxtLink to="/audit" class="text-xs text-fg-3 hover:text-fg-1">← Back to the audit log</NuxtLink>
    <h1 id="audit-event-not-found" class="mt-4 text-lg font-semibold text-fg-1">Event not found</h1>
    <p class="mt-1 max-w-[70ch] text-sm leading-3 text-fg-3">
      {{ eventId || "This event ID" }} is not in the preview event set. Audit records are append-only, so an unrecorded
      ID is never reconstructed here. The live audit stream is not connected.
    </p>
    <NuxtLink to="/audit" class="ix-button-secondary mt-4 inline-flex h-8 items-center text-xs">
      Browse recorded events
    </NuxtLink>
  </section>
</template>
