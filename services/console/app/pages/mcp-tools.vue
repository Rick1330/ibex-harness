<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import ToolListView from "@/components/console/tool/ToolListView.vue"
import {
  parseToolQuery,
  serializeToolQuery,
  type ToolListState,
} from "@/lib/tool-preview"

const route = useRoute()
const router = useRouter()
const state = ref<ToolListState>(parseToolQuery(route.query))

useHead({ title: "MCP tools · IBEX Console" })

function serialized(value: ToolListState): string {
  return serializeToolQuery(value).toString()
}

watch(
  state,
  (next) => {
    if (!import.meta.client) return
    if (serialized(next) === serialized(parseToolQuery(route.query))) return
    void router.replace({ query: Object.fromEntries(serializeToolQuery(next)) }).catch(() => undefined)
  },
  { deep: true },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/mcp-tools") return
    const parsed = parseToolQuery(route.query)
    if (serialized(parsed) !== serialized(state.value)) state.value = parsed
  },
)
</script>

<template>
  <ToolListView :state="state" @update="state = $event" />
</template>
