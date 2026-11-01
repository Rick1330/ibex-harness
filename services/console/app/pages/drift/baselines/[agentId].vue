<script setup lang="ts">
import { computed } from "vue"
import { useRoute } from "vue-router"
import DriftBaselineView from "@/components/console/drift/baseline/DriftBaselineView.vue"
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"
import { driftBaselineForAgent } from "@/lib/drift-preview"
import { driftBaselineListHref } from "@/lib/govern-query"

const route = useRoute()
const agentId = computed(() => String(route.params.agentId ?? ""))
const baseline = computed(() => driftBaselineForAgent(agentId.value))

useHead(() => ({
  title: baseline.value
    ? `${baseline.value.agent.name} baseline · Drift · IBEX Console`
    : "Baseline not found · Drift · IBEX Console",
}))
</script>

<template>
  <DriftBaselineView v-if="baseline" :baseline="baseline" />
  <section
    v-else
    class="mx-auto w-full max-w-[90rem] rounded-lg border border-line-subtle bg-surface-1 p-6"
    aria-labelledby="baseline-not-found"
  >
    <NuxtLink :to="driftBaselineListHref({ agent: 'all', age: 'all' })" class="text-xs text-fg-3 hover:text-fg-1">
      ← Back to baselines
    </NuxtLink>
    <h1 id="baseline-not-found" class="sr-only">Baseline not found</h1>
    <GovernEmptyState
      class="mt-4"
      title="No baseline · drift can't be detected"
      :reason="`${agentId || 'This agent version'} has no certified baseline in the recorded preview set. Without a baseline there is no band, so drift cannot be detected or compared.`"
      next-step="Browse the recorded baselines, or check the agent version in the Agents area."
      action-label="Browse baselines"
      @action="navigateTo(driftBaselineListHref({ agent: 'all', age: 'all' }))"
    />
  </section>
</template>
