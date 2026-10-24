<script setup lang="ts">
withDefaults(defineProps<{
  version: string
  type?: string
}>(), {
  type: 'stable',
})
</script>

<template>
  <span class="site-tag align-middle">
    v{{ version }} · {{ type }}
  </span>
</template>
