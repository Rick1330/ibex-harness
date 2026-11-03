<script setup lang="ts">
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import SettingsView from "@/components/console/settings/SettingsView.vue"
import { parseSettingsQuery, serializeSettingsQuery } from "@/lib/settings-query"
import type { SettingsSection } from "@/lib/settings-preview"

const route = useRoute()
const router = useRouter()
const section = ref<SettingsSection>(parseSettingsQuery(route.query))

useHead({ title: "Settings · IBEX Console" })

watch(
  section,
  (next) => {
    if (!import.meta.client) return
    if (next === parseSettingsQuery(route.query)) return
    void router.replace({ query: Object.fromEntries(serializeSettingsQuery(next)) }).catch(() => undefined)
  },
)

watch(
  () => route.query,
  () => {
    if (route.path !== "/settings") return
    const parsed = parseSettingsQuery(route.query)
    if (parsed !== section.value) section.value = parsed
  },
)
</script>

<template>
  <SettingsView :section="section" @update="section = $event" />
</template>
