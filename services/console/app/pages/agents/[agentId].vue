<script setup lang="ts">
import { computed } from "vue"
import AgentDetailView from "@/components/console/agent/detail/AgentDetailView.vue"
import { getAgentPreview } from "@/lib/agent-preview"
import { safeAgentReturn } from "@/lib/return-to"

const route = useRoute()
const agentId = computed(() => String(route.params.agentId ?? ""))
const agent = computed(() => getAgentPreview(agentId.value))
const returnTo = computed(() => safeAgentReturn(route.query.return))

useHead(() => ({
  title: `${agent.value?.name ?? "Agent not found"} · Agents · IBEX Console`,
}))
</script>

<template>
  <AgentDetailView v-if="agent" :agent="agent" :return-to="returnTo" />
  <section v-else class="mx-auto w-full max-w-[90rem] rounded-lg border border-line-subtle bg-surface-1 p-6" aria-labelledby="agent-not-found">
    <NuxtLink :to="returnTo" class="text-xs text-fg-3 hover:text-fg-1">← Back to agents</NuxtLink>
    <h1 id="agent-not-found" class="mt-4 text-lg font-semibold text-fg-1">Agent not found</h1>
    <p class="mt-1 text-sm text-fg-3">This sample agent ID is not in the preview set. Live agent lookups are not connected.</p>
  </section>
</template>
