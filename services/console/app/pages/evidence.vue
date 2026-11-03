<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import EvidenceView from "@/components/console/evidence/EvidenceView.vue"
import {
  parseLiveEvidenceQuery,
  parseLiveEvidenceQueryLenient,
  serializeLiveEvidenceQuery,
  type LiveEvidenceQuery,
} from "~~/shared/operator/evidence-query"

const route = useRoute()
const router = useRouter()
const state = ref<LiveEvidenceQuery>(stateFromQuery(route.query))

useHead({ title: "Evidence · IBEX Console" })

function strictStateFromQuery(query: Record<string, unknown>): LiveEvidenceQuery | null {
  try {
    return parseLiveEvidenceQuery(query)
  } catch {
    return null
  }
}

// A stale or hand-edited link must not silently reinterpret the read: keep the
// fields that parse and let `normalizeUrl` drop the rest from the address bar so
// it always describes the window on screen.
function stateFromQuery(query: Record<string, unknown>): LiveEvidenceQuery {
  return strictStateFromQuery(query) ?? parseLiveEvidenceQueryLenient(query)
}

function serialized(value: LiveEvidenceQuery): string {
  return serializeLiveEvidenceQuery(value).toString()
}

function normalizeUrl(): void {
  if (strictStateFromQuery(route.query)) return
  void router
    .replace({ query: Object.fromEntries(serializeLiveEvidenceQuery(state.value)) })
    .catch(() => undefined)
}

onMounted(normalizeUrl)

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    const current = strictStateFromQuery(route.query)
    if (current && serialized(next) === serialized(current)) return
    void router
      .replace({ query: Object.fromEntries(serializeLiveEvidenceQuery(next)) })
      .catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/evidence") return
    const strict = strictStateFromQuery(route.query)
    const parsed = strict ?? parseLiveEvidenceQueryLenient(route.query)
    // Assigning a fresh object also fires the state watcher, which rewrites the
    // address bar, so an ignored field cannot linger in the URL.
    if (strict && serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <EvidenceView :state="state" @update="state = $event" />
</template>
