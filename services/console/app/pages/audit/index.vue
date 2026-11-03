<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import AuditListView from "@/components/console/audit/list/AuditListView.vue"
import { parseAuditListQuery, serializeAuditListQuery, type AuditListQueryState } from "@/lib/govern-query"

const route = useRoute()
const router = useRouter()
const state = ref<AuditListQueryState>(parseAuditListQuery(route.query))

useHead({ title: "Audit log · IBEX Console" })

function serialized(value: AuditListQueryState): string {
  return serializeAuditListQuery(value).toString()
}

function queryFrom(value: AuditListQueryState): Record<string, string> {
  return Object.fromEntries(serializeAuditListQuery(value))
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseAuditListQuery(route.query))) return
    void router.replace({ query: queryFrom(next) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/audit") return
    const parsed = parseAuditListQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <AuditListView :state="state" @update="state = $event" />
</template>
