<script setup lang="ts">
import { computed } from "vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import MemoryDetailView from "@/components/console/memory/live/LiveMemoryDetailView.vue"
import { useOperatorMemory } from "@/composables/useOperatorData"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import { safeMemoryReturn } from "@/lib/return-to"

const route = useRoute()
const memoryId = computed(() => String(route.params.memoryId ?? ""))
const memoryState = useOperatorMemory(() => memoryId.value)
const memory = computed(() => memoryState.data.value ?? null)
const error = computed(() => memoryState.error.value)
const loading = computed(
  () => !memory.value && !error.value && memoryState.status.value === "pending",
)
const notFound = computed(
  () => (error.value as { statusCode?: number } | null)?.statusCode === 404,
)
const authIssue = computed(() => isOperatorAuthError(error.value))
const failureDetail = computed(() =>
  error.value && !notFound.value && !authIssue.value ? operatorFailureDetail(error.value) : null,
)
const returnTo = computed(() => safeMemoryReturn(route.query.return))

useHead(() => ({
  title: `Memory ${memoryId.value.slice(0, 8)} · Memories · IBEX Console`,
}))
</script>

<template>
  <MemoryDetailView v-if="memory" :memory="memory" :return-to="returnTo" />
  <div v-else class="flex min-w-0 flex-col gap-4">
    <NuxtLink :to="returnTo" class="inline-flex text-xs text-fg-3 hover:text-fg-1">
      ← Back to memories
    </NuxtLink>
    <IxVerdict
      v-if="loading"
      tone="unknown"
      eyebrow="Live operator read"
      title="Reading the memory record…"
      body="The console is waiting for the operator API."
    />
    <IxVerdict
      v-else-if="notFound"
      tone="unknown"
      eyebrow="Live operator read"
      title="Memory not found"
      body="This memory does not exist in the current organization, or the operator session cannot see it."
    />
    <IxVerdict
      v-else-if="authIssue"
      tone="unavailable"
      eyebrow="Live operator read"
      title="An operator session is required to read this memory"
      body="Sign in with a session that can read this organization. No fixture record is substituted."
    />
    <IxVerdict
      v-else
      tone="unavailable"
      eyebrow="Live operator read"
      title="Memory record unavailable"
      :body="failureDetail ?? 'The operator API did not return a verified record.'"
    />
  </div>
</template>
