<script setup lang="ts">
const props = withDefaults(defineProps<{
  code: string
  title?: string
}>(), {
  title: '',
})

const { isDark, render } = useMermaidDiagram()

const root = ref<HTMLElement | null>(null)
const canvas = ref<HTMLElement | null>(null)
const state = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const svg = ref('')
const naturalWidth = ref(0)
const naturalHeight = ref(0)
const viewerOpen = ref(false)

let observer: IntersectionObserver | null = null
let requestToken = 0

const label = computed(() => props.title || 'Diagram')

async function renderDiagram() {
  if (state.value === 'loading') return
  const token = ++requestToken
  state.value = 'loading'
  try {
    const result = await render(props.code)
    if (token !== requestToken) return
    svg.value = result.svg
    naturalWidth.value = result.width
    naturalHeight.value = result.height
    state.value = 'ready'
    await nextTick()
    const element = canvas.value?.querySelector('svg')
    if (element) result.bindFunctions?.(element)
  } catch {
    if (token !== requestToken) return
    svg.value = ''
    state.value = 'error'
  }
}

watch(isDark, () => {
  if (state.value === 'ready' || state.value === 'error') void renderDiagram()
})

onMounted(() => {
  if (!('IntersectionObserver' in window)) {
    void renderDiagram()
    return
  }

  observer = new IntersectionObserver((entries) => {
    if (!entries.some(entry => entry.isIntersecting)) return
    observer?.disconnect()
    observer = null
    void renderDiagram()
  }, { rootMargin: '600px 0px' })

  if (root.value) observer.observe(root.value)
})

onBeforeUnmount(() => {
  requestToken += 1
  observer?.disconnect()
})
</script>

<template>
  <figure ref="root" class="mermaid-figure" :style="{ '--diagram-width': `${naturalWidth}px` }">
    <figcaption class="mermaid-figure__bar">
      <span class="mermaid-figure__label">
        <UIcon name="i-lucide-workflow" class="size-3.5" aria-hidden="true" />
        {{ label }}
      </span>
      <button
        v-if="state === 'ready'"
        type="button"
        class="mermaid-figure__expand"
        :aria-label="`Expand ${label}`"
        @click="viewerOpen = true"
      >
        <UIcon name="i-lucide-maximize-2" class="size-3.5" aria-hidden="true" />
        <span class="hidden sm:inline">Expand</span>
      </button>
    </figcaption>

    <div
      ref="canvas"
      class="mermaid-figure__canvas"
      :aria-busy="state === 'loading' ? 'true' : 'false'"
    >
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div
        v-if="state === 'ready'"
        class="mermaid-figure__svg"
        role="group"
        :aria-label="label"
        v-html="svg"
      />
      <div v-else-if="state === 'error'" class="mermaid-figure__error">
        <p class="m-0 flex items-center gap-2 font-mono text-[0.58rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">
          <UIcon name="i-lucide-triangle-alert" class="size-3.5 text-[var(--chart-orange)]" aria-hidden="true" />
          Diagram source could not be rendered
        </p>
        <pre class="mermaid-figure__source"><code>{{ props.code }}</code></pre>
      </div>
      <div v-else class="mermaid-figure__loading">
        <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" aria-hidden="true" />
        <span>Rendering diagram</span>
      </div>
    </div>
  </figure>

  <DiagramViewer
    :open="viewerOpen"
    :code="props.code"
    :title="label"
    @close="viewerOpen = false"
  />
</template>

<style scoped>
.mermaid-figure {
  margin: 1.5rem 0;
  overflow: hidden;
  border: 1px solid var(--site-line);
  border-radius: 0.85rem;
  background: color-mix(in srgb, var(--site-surface) 80%, transparent);
}

.mermaid-figure__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0.8rem;
  border-bottom: 1px solid color-mix(in srgb, var(--site-line) 70%, transparent);
}

.mermaid-figure__label {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.mermaid-figure__expand {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border-radius: 0.4rem;
  padding: 0.3rem 0.55rem;
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-muted);
  transition: color 160ms ease, background-color 160ms ease;
}

.mermaid-figure__expand:hover {
  background: color-mix(in srgb, var(--site-ink) 7%, transparent);
  color: var(--site-ink);
}

.mermaid-figure__expand:focus-visible {
  outline: 2px solid var(--site-signal);
  outline-offset: 2px;
}

.mermaid-figure__canvas {
  overflow-x: auto;
  overflow-y: hidden;
  padding: 1.15rem 1.1rem;
}

.mermaid-figure__svg :deep(svg) {
  display: block;
  margin-inline: auto;
  height: auto;
}

@media (max-width: 767px) {
  .mermaid-figure__canvas {
    padding: 0.9rem 0.7rem;
  }

  .mermaid-figure__svg :deep(svg) {
    min-width: min(680px, var(--diagram-width, 0px));
  }
}

.mermaid-figure__loading {
  display: flex;
  min-height: 9rem;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.mermaid-figure__error {
  display: grid;
  gap: 0.75rem;
}

.mermaid-figure__source {
  margin: 0;
  max-height: 14rem;
  overflow: auto;
  border-radius: 0.55rem;
  border: 1px solid var(--site-line);
  background: var(--site-code-bg);
  padding: 0.85rem;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  line-height: 1.55;
  color: var(--site-ink);
}
</style>
