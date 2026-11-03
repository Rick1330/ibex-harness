<script setup lang="ts">
import GovernEmptyState from "@/components/console/govern/primitives/GovernEmptyState.vue"

const props = defineProps<{
  title: string
  reason: string
  nextStep: string
  actionLabel: string
  actionTo: string
}>()

function go(): void {
  void navigateTo(props.actionTo)
}
</script>

<template>
  <GovernEmptyState
    :title="title"
    :reason="reason"
    :next-step="nextStep"
    :action-label="actionLabel"
    @action="go"
  />
</template>
