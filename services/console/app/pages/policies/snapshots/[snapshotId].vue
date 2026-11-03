<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"
import PolicySnapshotView from "@/components/console/policy/snapshot/PolicySnapshotView.vue"
import { policySnapshotById } from "@/lib/policy-preview"
import {
  parsePolicySnapshotDetailQuery,
  serializePolicySnapshotDetailQuery,
  type PolicySnapshotDetailState,
} from "@/lib/govern-query"
import { safePolicyReturn } from "@/lib/return-to"

const route = useRoute()
const snapshotId = computed(() => String(route.params.snapshotId ?? ""))
const snapshot = computed(() => policySnapshotById(snapshotId.value))
const state = ref<PolicySnapshotDetailState>(parsePolicySnapshotDetailQuery(route.query))
const returnTo = computed(() => safePolicyReturn(route.query.return))

watch(
  () => route.query,
  () => {
    if (!route.path.startsWith("/policies/snapshots/")) return
    state.value = parsePolicySnapshotDetailQuery(route.query)
  },
)

function update(next: PolicySnapshotDetailState): void {
  state.value = next
  if (!import.meta.client) return
  const query = Object.fromEntries(serializePolicySnapshotDetailQuery(next))
  const preserved = typeof route.query.return === "string" ? { return: route.query.return } : {}
  void navigateTo({ query: { ...query, ...preserved } }, { replace: true })
}

useHead(() => ({
  title: `${snapshot.value?.id ?? "Snapshot not found"} · Policies · IBEX Console`,
}))
</script>

<template>
  <PolicySnapshotView
    v-if="snapshot"
    :snapshot="snapshot"
    :state="state"
    :return-to="returnTo"
    @update="update"
  />
  <section
    v-else
    class="mx-auto w-full max-w-[90rem] rounded-lg border border-line-subtle bg-surface-1 p-6"
    aria-labelledby="snapshot-not-found"
  >
    <NuxtLink :to="returnTo" class="text-xs text-fg-3 hover:text-fg-1">← Back to policies</NuxtLink>
    <h1 id="snapshot-not-found" class="mt-4 text-lg font-semibold text-fg-1">Snapshot not found</h1>
    <p class="max-w-[70ch] text-sm text-fg-3">
      {{ snapshotId || "This snapshot ID" }} is not in the preview snapshot set. Snapshots are immutable records, so
      an unrecorded ID is never reconstructed here. Live policy storage is not connected.
    </p>
    <NuxtLink to="/policies?tab=snapshots" class="ix-button-secondary mt-4 inline-flex h-8 items-center text-xs">
      Browse recorded snapshots
    </NuxtLink>
  </section>
</template>
