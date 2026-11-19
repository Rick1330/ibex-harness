<script setup lang="ts">
defineProps<{
  id: string
  title: string
}>()
</script>

<template>
  <section :id="id" class="console-panel scroll-mt-20">
    <header class="console-panel-header">
      <div class="min-w-0">
        <h2 class="text-[0.625rem] font-medium tracking-[0.12em] text-fg-3 uppercase">{{ title }}</h2>
      </div>
      <div v-if="$slots.actions" class="flex shrink-0 flex-wrap items-center gap-2">
        <slot name="actions" />
      </div>
    </header>
    <slot />
  </section>
</template>
