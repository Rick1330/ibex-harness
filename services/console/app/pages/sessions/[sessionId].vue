<script setup lang="ts">
import { computed } from "vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import LiveSessionDetailView from "@/components/console/session/live/LiveSessionDetailView.vue"
import { useOperatorSession } from "@/composables/useOperatorData"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import { safeSessionReturn } from "@/lib/return-to"

const route = useRoute()
const sessionId = computed(() => String(route.params.sessionId ?? ""))
const sessionState = useOperatorSession(() => sessionId.value)
const session = computed(() => sessionState.data.value ?? null)
const error = computed(() => sessionState.error.value)
const loading = computed(
  () => !session.value && !error.value && sessionState.status.value === "pending",
)
const notFound = computed(
  () => (error.value as { statusCode?: number } | null)?.statusCode === 404,
)
const authIssue = computed(() => isOperatorAuthError(error.value))
const failureDetail = computed(() =>
  error.value && !notFound.value && !authIssue.value ? operatorFailureDetail(error.value) : null,
)
const returnTo = computed(() => safeSessionReturn(route.query.return))

useHead(() => ({
  title: `Session ${sessionId.value.slice(0, 8)} · Sessions · IBEX Console`,
}))
</script>

<template>
  <LiveSessionDetailView v-if="session" :session="session" :return-to="returnTo" />
  <div v-else class="flex min-w-0 flex-col gap-4">
    <NuxtLink :to="returnTo" class="inline-flex text-xs text-fg-3 hover:text-fg-1">
      ← Back to sessions
    </NuxtLink>
    <IxVerdict
      v-if="loading"
      tone="unknown"
      eyebrow="Live operator read"
      title="Reading the session record…"
      body="The console is waiting for the operator API."
    />
    <IxVerdict
      v-else-if="notFound"
      tone="unknown"
      eyebrow="Live operator read"
      title="Session not found"
      body="This session does not exist in the current organization, was logically deleted, or the operator session cannot see it."
    />
    <IxVerdict
      v-else-if="authIssue"
      tone="unavailable"
      eyebrow="Live operator read"
      title="An operator session is required to read this session"
      body="Sign in with a session that can read this organization. No fixture record is substituted."
    />
    <IxVerdict
      v-else
      tone="unavailable"
      eyebrow="Live operator read"
      title="Session record unavailable"
      :body="failureDetail ?? 'The operator API did not return a verified record.'"
    />
  </div>
</template>
