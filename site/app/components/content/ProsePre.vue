<script setup lang="ts">
import type { PropType } from 'vue'
import ProsePreBase from '@nuxt/ui/components/prose/Pre.vue'
import MermaidDiagram from './MermaidDiagram.vue'

const props = defineProps({
  code: { type: String, default: '' },
  language: { type: String, default: null },
  filename: { type: String, default: null },
  highlights: { type: Array as PropType<number[]>, default: () => [] },
  meta: { type: String, default: null },
  class: { type: [String, Array, Object], default: null },
  ui: { type: Object, default: undefined },
})

const isMermaid = computed(() => props.language?.toLowerCase() === 'mermaid')
const diagramTitle = computed(() => props.meta?.match(/(?:^|\s)title="([^"]+)"/)?.[1] ?? '')
</script>

<template>
  <MermaidDiagram
    v-if="isMermaid"
    :code="props.code"
    :title="diagramTitle || undefined"
  />
  <ProsePreBase v-else v-bind="{ ...props, ...$attrs }">
    <slot />
  </ProsePreBase>
</template>
