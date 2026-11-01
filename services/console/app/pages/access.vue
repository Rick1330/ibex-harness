<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import AccessView from "@/components/console/access/AccessView.vue"
import { parseAccessQuery, serializeAccessQuery, type AccessState } from "@/lib/access-query"

const route = useRoute()
const router = useRouter()
const state = ref<AccessState>(parseAccessQuery(route.query))

useHead({ title: "Access · IBEX Console" })

function serialized(value: AccessState): string {
  return serializeAccessQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseAccessQuery(route.query))) return
    void router.replace({ query: Object.fromEntries(serializeAccessQuery(next)) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/access") return
    const parsed = parseAccessQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <AccessView :state="state" @update="state = $event" />
</template>
