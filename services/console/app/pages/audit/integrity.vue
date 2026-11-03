<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import AuditIntegrityView from "@/components/console/audit/integrity/AuditIntegrityView.vue"
import {
  parseAuditIntegrityQuery,
  serializeAuditIntegrityQuery,
  type AuditIntegrityState,
} from "@/lib/govern-query"

const route = useRoute()
const router = useRouter()
const state = ref<AuditIntegrityState>(parseAuditIntegrityQuery(route.query))

useHead({ title: "Audit integrity · IBEX Console" })

function serialized(value: AuditIntegrityState): string {
  return serializeAuditIntegrityQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseAuditIntegrityQuery(route.query))) return
    void router
      .replace({ query: Object.fromEntries(serializeAuditIntegrityQuery(next)) })
      .catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/audit/integrity") return
    const parsed = parseAuditIntegrityQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <AuditIntegrityView :state="state" @update="state = $event" />
</template>
