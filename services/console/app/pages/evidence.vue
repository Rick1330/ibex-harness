<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import EvidenceView from "@/components/console/evidence/EvidenceView.vue"
import { parseEvidenceQuery, serializeEvidenceQuery, type EvidenceListState } from "@/lib/govern-query"

const route = useRoute()
const router = useRouter()
const state = ref<EvidenceListState>(parseEvidenceQuery(route.query))

useHead({ title: "Evidence · IBEX Console" })

function serialized(value: EvidenceListState): string {
  return serializeEvidenceQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseEvidenceQuery(route.query))) return
    void router.replace({ query: Object.fromEntries(serializeEvidenceQuery(next)) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/evidence") return
    const parsed = parseEvidenceQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <EvidenceView :state="state" @update="state = $event" />
</template>
