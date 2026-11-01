<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"
import DirectiveDetailView from "@/components/console/directive/detail/DirectiveDetailView.vue"
import { directiveCandidate, directiveLive, getDirectivePreview } from "@/lib/directive-preview"
import {
  parseDirectiveDetailQuery,
  serializeDirectiveDetailQuery,
  type DirectiveDetailState,
} from "@/lib/govern-query"
import { safeDirectiveReturn } from "@/lib/return-to"

const route = useRoute()
const directiveId = computed(() => String(route.params.directiveId ?? ""))
const directive = computed(() => getDirectivePreview(directiveId.value))
const returnTo = computed(() => safeDirectiveReturn(route.query.return))

const defaults = computed(() => {
  const value = directive.value
  if (!value) return { from: "v1", to: "v1" }
  const to = directiveCandidate(value) ?? directiveLive(value) ?? value.versions[0] ?? null
  if (!to) return { from: "v1", to: "v1" }
  const index = value.versions.findIndex((version) => version.version === to.version)
  const from = (index >= 0 ? value.versions[index + 1] : undefined) ?? to
  return { from: from.version, to: to.version }
})

const state = ref<DirectiveDetailState>(parseDirectiveDetailQuery(route.query, defaults.value))

watch(
  () => route.query,
  () => {
    if (!route.path.startsWith("/directives/")) return
    state.value = parseDirectiveDetailQuery(route.query, defaults.value)
  },
)

watch(
  defaults,
  (next) => {
    state.value = parseDirectiveDetailQuery(route.query, next)
  },
)

function update(next: DirectiveDetailState): void {
  state.value = next
  if (!import.meta.client) return
  const query = Object.fromEntries(serializeDirectiveDetailQuery(next, defaults.value))
  const preserved = typeof route.query.return === "string" ? { return: route.query.return } : {}
  void navigateTo({ query: { ...query, ...preserved } }, { replace: true })
}

useHead(() => ({
  title: `${directive.value?.name ?? "Directive not found"} · Directives · IBEX Console`,
}))
</script>

<template>
  <DirectiveDetailView v-if="directive" :directive="directive" :return-to="returnTo" :state="state" :defaults="defaults" @update="update" />
  <section v-else class="mx-auto w-full max-w-[90rem] rounded-lg border border-line-subtle bg-surface-1 p-6" aria-labelledby="directive-not-found">
    <NuxtLink :to="returnTo" class="text-xs text-fg-3 hover:text-fg-1">← Back to directives</NuxtLink>
    <h1 id="directive-not-found" class="mt-4 text-lg font-semibold text-fg-1">Directive not found</h1>
    <p class="mt-1 text-sm text-fg-3">This sample directive ID is not in the preview set. Live directive lookups are not connected.</p>
  </section>
</template>
