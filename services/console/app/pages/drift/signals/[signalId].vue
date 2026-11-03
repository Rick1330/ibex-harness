<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"
import DriftSignalView from "@/components/console/drift/detail/DriftSignalView.vue"
import { driftSignalById } from "@/lib/drift-preview"
import {
  driftListHref,
  DRIFT_LIST_DEFAULT,
  parseDriftSignalDetailQuery,
  serializeDriftSignalDetailQuery,
  type DriftSignalDetailState,
} from "@/lib/govern-query"

const route = useRoute()
const signalId = computed(() => String(route.params.signalId ?? ""))
const signal = computed(() => driftSignalById(signalId.value))
const state = ref<DriftSignalDetailState>(parseDriftSignalDetailQuery(route.query))

watch(
  () => route.query,
  () => {
    if (!route.path.startsWith("/drift/signals/")) return
    const parsed = parseDriftSignalDetailQuery(route.query)
    if (serializeDriftSignalDetailQuery(parsed).toString() === serializeDriftSignalDetailQuery(state.value).toString()) return
    state.value = parsed
  },
)

function update(next: DriftSignalDetailState): void {
  state.value = next
  if (!import.meta.client) return
  const query = Object.fromEntries(serializeDriftSignalDetailQuery(next))
  void navigateTo({ query }, { replace: true })
}

useHead(() => ({
  title: `${signal.value?.metric ?? "Signal not found"} · Drift · IBEX Console`,
}))
</script>

<template>
  <DriftSignalView v-if="signal" :signal="signal" :state="state" @update="update" />
  <section
    v-else
    class="mx-auto w-full max-w-[90rem] rounded-lg border border-line-subtle bg-surface-1 p-6"
    aria-labelledby="drift-signal-not-found"
  >
    <NuxtLink :to="driftListHref(DRIFT_LIST_DEFAULT)" class="text-xs text-fg-3 hover:text-fg-1">← Back to drift</NuxtLink>
    <h1 id="drift-signal-not-found" class="mt-4 text-lg font-semibold text-fg-1">Signal not found</h1>
    <p class="max-w-[70ch] text-sm text-fg-3">
      {{ signalId || "This signal ID" }} is not in the recorded preview set. Signals are never reconstructed from a
      guessed ID, and no live drift read model is connected to this console.
    </p>
    <NuxtLink to="/drift" class="ix-button-secondary mt-4 inline-flex h-8 items-center text-xs">
      Browse recorded signals
    </NuxtLink>
  </section>
</template>
