<script setup lang="ts">
import { computed } from "vue"
import AgentDetailView from "@/components/console/agent/detail/AgentDetailView.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import { useOperatorAgent } from "@/composables/useOperatorData"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import { safeAgentReturn } from "@/lib/return-to"

const route = useRoute()
const agentId = computed(() => String(route.params.agentId ?? ""))
const agentState = useOperatorAgent(() => agentId.value)
const agent = computed(() => agentState.data.value ?? null)
const error = computed(() => agentState.error.value)
const loading = computed(
  () => !agent.value && !error.value && agentState.status.value === "pending",
)
const notFound = computed(
  () => (error.value as { statusCode?: number } | null)?.statusCode === 404,
)
const authIssue = computed(() => isOperatorAuthError(error.value))
const failureDetail = computed(() =>
  error.value && !notFound.value && !authIssue.value ? operatorFailureDetail(error.value) : null,
)
const returnTo = computed(() => safeAgentReturn(route.query.return))

useHead(() => ({
  title: `${agent.value?.name ?? "Agent"} · Agents · IBEX Console`,
}))
</script>

<template>
  <AgentDetailView v-if="agent" :agent="agent" :return-to="returnTo" />
  <div v-else class="flex min-w-0 flex-col gap-4">
    <NuxtLink :to="returnTo" class="inline-flex text-xs text-fg-3 hover:text-fg-1">
      ← Back to agents
    </NuxtLink>
    <IxVerdict
      v-if="loading"
      tone="unknown"
      eyebrow="Live operator read"
      title="Reading the agent record…"
      body="The console is waiting for the operator API."
    />
    <IxVerdict
      v-else-if="notFound"
      tone="unknown"
      eyebrow="Live operator read"
      title="Agent not found"
      body="This agent does not exist in the current organization, or the operator session cannot see it."
    />
    <IxVerdict
      v-else-if="authIssue"
      tone="unavailable"
      eyebrow="Live operator read"
      title="An operator session is required to read this agent"
      body="Sign in with a session that can read this organization. No fixture record is substituted."
    />
    <IxVerdict
      v-else
      tone="unavailable"
      eyebrow="Live operator read"
      title="Agent record unavailable"
      :body="failureDetail ?? 'The operator API did not return a verified record.'"
    />
  </div>
</template>
