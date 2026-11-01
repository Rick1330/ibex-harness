<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import PlatformView from "@/components/console/platform/PlatformView.vue"
import { parsePlatformQuery, serializePlatformQuery, type PlatformState } from "@/lib/govern-query"

const route = useRoute()
const router = useRouter()
const state = ref<PlatformState>(parsePlatformQuery(route.query))

useHead({ title: "Platform · IBEX Console" })

function serialized(value: PlatformState): string {
  return serializePlatformQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parsePlatformQuery(route.query))) return
    void router.replace({ query: Object.fromEntries(serializePlatformQuery(next)) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/platform") return
    const parsed = parsePlatformQuery(route.query)
    if (serialized(parsed) === serialized(state.value)) return
    state.value = parsed
  },
)
</script>

<template>
  <PlatformView :state="state" @update="state = $event" />
</template>
