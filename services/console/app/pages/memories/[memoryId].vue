<script setup lang="ts">
import { computed } from "vue"
import { getMemoryDetail, memoryTitle } from "@/lib/memory-detail-preview"
import { safeMemoryReturn } from "@/lib/return-to"

const route = useRoute()
const memoryId = computed(() => String(route.params.memoryId ?? ""))
const detail = computed(() => getMemoryDetail(memoryId.value))
const returnTo = computed(() => safeMemoryReturn(route.query.return))

useHead(() => ({
  title: `${detail.value ? memoryTitle(detail.value.memory.id) : "Memory not available"} · Memory · IBEX Console`,
}))
</script>

<template>
  <MemoryDetailView :detail="detail" :memory-id="memoryId" :return-to="returnTo" />
</template>
