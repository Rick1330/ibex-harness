<script setup lang="ts">
defineProps<{
  keys: string[]
}>()
</script>

<template>
  <span class="inline-flex items-center gap-1 align-middle">
    <UKbd v-for="key in keys" :key="key" :value="key" />
  </span>
</template>
