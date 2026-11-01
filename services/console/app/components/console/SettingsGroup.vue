<script setup lang="ts">
withDefaults(
  defineProps<{
    id: string
    title: string
    definition?: string | null
  }>(),
  { definition: null },
)
</script>

<template>
  <section :id="id" class="console-panel scroll-mt-20">
    <header class="console-panel-header">
      <div class="min-w-0">
        <h2 class="text-[0.625rem] font-medium tracking-[0.12em] text-fg-3 uppercase">{{ title }}</h2>
        <p v-if="definition" class="mt-1 max-w-2xl text-[0.6875rem] leading-4 text-fg-3 text-pretty">{{ definition }}</p>
      </div>
      <div v-if="$slots.actions" class="flex shrink-0 flex-wrap items-center gap-2">
        <slot name="actions" />
      </div>
    </header>
    <slot />
  </section>
</template>
