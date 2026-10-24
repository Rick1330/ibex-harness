<script setup lang="ts">
const props = withDefaults(defineProps<{
  open: boolean
  code: string
  title?: string
}>(), {
  title: 'Diagram',
})

const emit = defineEmits<{ close: [] }>()

const { isDark, render } = useMermaidDiagram()

const titleId = useId()
const panel = ref<HTMLElement | null>(null)
const viewport = ref<HTMLElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
const state = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const svg = ref('')
const naturalWidth = ref(0)
const naturalHeight = ref(0)
const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const copied = ref(false)
const notice = ref('')

let restoreFocus: HTMLElement | null = null
let previousOverflow = ''
let lastDark = false
let copyTimer: ReturnType<typeof setTimeout> | null = null
let noticeTimer: ReturnType<typeof setTimeout> | null = null
let requestToken = 0

const pointers = new Map<number, { x: number, y: number }>()
let drag: { x: number, y: number, translateX: number, translateY: number } | null = null
let pinch: { distance: number, scale: number, translateX: number, translateY: number, midpoint: { x: number, y: number } } | null = null

const scaleLabel = computed(() => `${Math.round(scale.value * 100)}%`)
const slug = computed(() => (props.title || 'ibex-diagram')
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, '-')
  .replace(/^-+|-+$/g, '') || 'ibex-diagram')

const stageStyle = computed(() => ({
  width: `${naturalWidth.value}px`,
  height: `${naturalHeight.value}px`,
  transform: `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`,
}))

function clampScale(value: number) {
  return Math.min(8, Math.max(0.1, value))
}

function fitWidth() {
  const element = viewport.value
  if (!element || !naturalWidth.value || !naturalHeight.value) return
  const width = element.clientWidth
  const height = element.clientHeight
  const safe = clampScale(Math.max(0.85, Math.min((width - 64) / naturalWidth.value, 1.25)))
  const renderedWidth = naturalWidth.value * safe
  const renderedHeight = naturalHeight.value * safe
  scale.value = safe
  translateX.value = renderedWidth < width ? (width - renderedWidth) / 2 : 32
  translateY.value = renderedHeight < height ? (height - renderedHeight) / 2 : 32
}

function fitAll() {
  const element = viewport.value
  if (!element || !naturalWidth.value || !naturalHeight.value) return
  const width = element.clientWidth
  const height = element.clientHeight
  const safe = clampScale(Math.min((width - 64) / naturalWidth.value, (height - 64) / naturalHeight.value, 1.5))
  scale.value = safe
  translateX.value = (width - naturalWidth.value * safe) / 2
  translateY.value = (height - naturalHeight.value * safe) / 2
}

function fitInitial() {
  const element = viewport.value
  if (!element || !naturalWidth.value || !naturalHeight.value) return
  const contain = Math.min(
    (element.clientWidth - 64) / naturalWidth.value,
    (element.clientHeight - 64) / naturalHeight.value,
  )
  if (contain < 0.5) fitWidth()
  else fitAll()
}

function zoomAt(x: number, y: number, factor: number) {
  const next = clampScale(scale.value * factor)
  if (next === scale.value) return
  translateX.value = x - (x - translateX.value) * (next / scale.value)
  translateY.value = y - (y - translateY.value) * (next / scale.value)
  scale.value = next
}

function zoomFromCenter(factor: number) {
  const element = viewport.value
  if (!element) return
  zoomAt(element.clientWidth / 2, element.clientHeight / 2, factor)
}

function actualSize() {
  const element = viewport.value
  if (!element) return
  scale.value = 1
  translateX.value = (element.clientWidth - naturalWidth.value) / 2
  translateY.value = (element.clientHeight - naturalHeight.value) / 2
}

async function renderDiagram() {
  const token = ++requestToken
  state.value = 'loading'
  lastDark = isDark.value
  try {
    const result = await render(props.code, 'ibex-diagram-viewer')
    if (token !== requestToken) return
    svg.value = result.svg
    naturalWidth.value = result.width
    naturalHeight.value = result.height
    state.value = 'ready'
    await nextTick()
    fitInitial()
  } catch {
    if (token !== requestToken) return
    svg.value = ''
    state.value = 'error'
  }
}

async function onOpen() {
  restoreFocus = document.activeElement as HTMLElement | null
  previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  await nextTick()
  closeButton.value?.focus()
  if (state.value === 'ready' && lastDark === isDark.value) {
    fitInitial()
  } else {
    await renderDiagram()
  }
}

function onClose() {
  document.body.style.overflow = previousOverflow
  restoreFocus?.focus()
  emit('close')
}

watch(() => props.open, (open) => {
  if (!import.meta.client) return
  if (open) void onOpen()
  else document.body.style.overflow = previousOverflow
})

watch(isDark, () => {
  if (!props.open) return
  if (state.value === 'ready' || state.value === 'error') void renderDiagram()
})

function focusableElements() {
  if (!panel.value) return []
  return [...panel.value.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')]
    .filter(element => element.offsetParent !== null)
}

function onKeydown(event: KeyboardEvent) {
  if (!props.open) return

  if (event.key === 'Escape') {
    event.preventDefault()
    onClose()
    return
  }

  if (event.key === 'Tab') {
    const focusable = focusableElements()
    if (!focusable.length) return
    const first = focusable[0]!
    const last = focusable[focusable.length - 1]!
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
    return
  }

  if (event.metaKey || event.ctrlKey || event.altKey) return

  if (event.key === '+' || event.key === '=') {
    event.preventDefault()
    zoomFromCenter(1.2)
  } else if (event.key === '-' || event.key === '_') {
    event.preventDefault()
    zoomFromCenter(1 / 1.2)
  } else if (event.key === '0') {
    event.preventDefault()
    fitAll()
  } else if (event.key === '1') {
    event.preventDefault()
    actualSize()
  } else if (event.key.startsWith('Arrow')) {
    event.preventDefault()
    const step = event.shiftKey ? 160 : 60
    if (event.key === 'ArrowLeft') translateX.value += step
    if (event.key === 'ArrowRight') translateX.value -= step
    if (event.key === 'ArrowUp') translateY.value += step
    if (event.key === 'ArrowDown') translateY.value -= step
  }
}

function onWheel(event: WheelEvent) {
  if (!props.open || !viewport.value) return
  event.preventDefault()
  const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY
  const rect = viewport.value.getBoundingClientRect()
  zoomAt(event.clientX - rect.left, event.clientY - rect.top, Math.exp(-delta * 0.0015))
}

function onPointerDown(event: PointerEvent) {
  if (!viewport.value) return
  if (event.pointerType === 'mouse' && event.button !== 0) return
  viewport.value.setPointerCapture(event.pointerId)
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })

  if (pointers.size === 1) {
    drag = {
      x: event.clientX,
      y: event.clientY,
      translateX: translateX.value,
      translateY: translateY.value,
    }
    pinch = null
  } else if (pointers.size === 2) {
    const [first, second] = [...pointers.values()]
    const rect = viewport.value.getBoundingClientRect()
    const midpoint = {
      x: (first!.x + second!.x) / 2 - rect.left,
      y: (first!.y + second!.y) / 2 - rect.top,
    }
    pinch = {
      distance: Math.hypot(first!.x - second!.x, first!.y - second!.y) || 1,
      scale: scale.value,
      translateX: translateX.value,
      translateY: translateY.value,
      midpoint,
    }
    drag = null
  }
}

function onPointerMove(event: PointerEvent) {
  if (!pointers.has(event.pointerId) || !viewport.value) return
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })

  if (pointers.size === 2 && pinch) {
    const [first, second] = [...pointers.values()]
    const rect = viewport.value.getBoundingClientRect()
    const midpoint = {
      x: (first!.x + second!.x) / 2 - rect.left,
      y: (first!.y + second!.y) / 2 - rect.top,
    }
    const distance = Math.hypot(first!.x - second!.x, first!.y - second!.y) || 1
    const next = clampScale(pinch.scale * (distance / pinch.distance))
    const contentX = (pinch.midpoint.x - pinch.translateX) / pinch.scale
    const contentY = (pinch.midpoint.y - pinch.translateY) / pinch.scale
    scale.value = next
    translateX.value = midpoint.x - contentX * next
    translateY.value = midpoint.y - contentY * next
  } else if (pointers.size === 1 && drag) {
    translateX.value = drag.translateX + (event.clientX - drag.x)
    translateY.value = drag.translateY + (event.clientY - drag.y)
  }
}

function onPointerEnd(event: PointerEvent) {
  pointers.delete(event.pointerId)
  if (!pointers.size) {
    drag = null
    pinch = null
    return
  }
  if (pointers.size === 1) {
    const [point] = [...pointers.values()]
    drag = {
      x: point!.x,
      y: point!.y,
      translateX: translateX.value,
      translateY: translateY.value,
    }
    pinch = null
  }
}

function onDoubleClick(event: MouseEvent) {
  if (!viewport.value) return
  const rect = viewport.value.getBoundingClientRect()
  zoomAt(event.clientX - rect.left, event.clientY - rect.top, scale.value < 1.2 ? 2 : 0.5)
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function downloadSvg() {
  if (!svg.value) return
  downloadBlob(new Blob([svg.value], { type: 'image/svg+xml;charset=utf-8' }), `${slug.value}.svg`)
}

async function downloadPng() {
  if (!svg.value || !naturalWidth.value || !naturalHeight.value) return
  try {
    const exported = await render(props.code, 'ibex-diagram-export', { htmlLabels: false })
    const ratio = Math.min(2, 4096 / Math.max(exported.width, exported.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(exported.width * ratio)
    canvas.height = Math.round(exported.height * ratio)
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Canvas unavailable')

    const background = getComputedStyle(document.documentElement).getPropertyValue('--site-surface').trim() || '#ffffff'
    context.fillStyle = background
    context.fillRect(0, 0, canvas.width, canvas.height)

    const url = URL.createObjectURL(new Blob([exported.svg], { type: 'image/svg+xml;charset=utf-8' }))
    try {
      const image = new Image()
      image.decoding = 'async'
      await new Promise<void>((resolve, reject) => {
        image.onload = () => resolve()
        image.onerror = () => reject(new Error('SVG decode failed'))
        image.src = url
      })
      context.drawImage(image, 0, 0, canvas.width, canvas.height)
    } finally {
      URL.revokeObjectURL(url)
    }

    const png = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/png'))
    if (png) downloadBlob(png, `${slug.value}.png`)
  } catch {
    notice.value = 'PNG export is unavailable in this browser.'
    if (noticeTimer) clearTimeout(noticeTimer)
    noticeTimer = setTimeout(() => { notice.value = '' }, 3000)
  }
}

async function copySource() {
  try {
    await navigator.clipboard.writeText(props.code)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = props.code
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    textarea.remove()
  }
  copied.value = true
  if (copyTimer) clearTimeout(copyTimer)
  copyTimer = setTimeout(() => { copied.value = false }, 1600)
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  requestToken += 1
  window.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = previousOverflow
  if (copyTimer) clearTimeout(copyTimer)
  if (noticeTimer) clearTimeout(noticeTimer)
})
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="props.open"
        class="fixed inset-0 z-[90] flex items-stretch justify-center bg-black/75 backdrop-blur-sm sm:items-center sm:p-4"
        @click.self="onClose"
      >
        <div
          ref="panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          class="flex h-full w-full flex-col overflow-hidden border border-[var(--site-line)] bg-[var(--site-bg)] shadow-[0_40px_120px_-30px_#000] sm:h-[94dvh] sm:max-w-[98vw] sm:rounded-2xl"
        >
          <header class="flex shrink-0 items-start gap-4 border-b border-[var(--site-line)] px-4 py-3 sm:px-6 sm:py-4">
            <div class="min-w-0 flex-1">
              <p class="m-0 font-mono text-[0.52rem] uppercase tracking-[0.14em] text-[var(--site-signal)]">
                Expanded view
              </p>
              <h2 :id="titleId" class="m-0 mt-0.5 truncate text-base font-medium tracking-[-0.02em] sm:text-lg">
                {{ props.title }}
              </h2>
            </div>
            <button
              ref="closeButton"
              type="button"
              class="grid size-8 shrink-0 place-items-center rounded-md text-[var(--site-muted)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_7%,transparent)] hover:text-[var(--site-ink)]"
              aria-label="Close diagram"
              @click="onClose"
            >
              <UIcon name="i-lucide-x" class="size-4" />
            </button>
          </header>

          <div class="flex shrink-0 flex-nowrap items-center gap-1 overflow-x-auto border-b border-[var(--site-line)] bg-[color-mix(in_srgb,var(--site-surface)_70%,transparent)] px-3 py-2 [scrollbar-width:none] sm:px-5">
            <div class="flex shrink-0 items-center rounded-md border border-[var(--site-line)] bg-[var(--site-bg)]">
              <button
                type="button"
                class="grid size-8 place-items-center rounded-l-md text-[var(--site-muted)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_7%,transparent)] hover:text-[var(--site-ink)]"
                aria-label="Zoom out"
                @click="zoomFromCenter(1 / 1.2)"
              >
                <UIcon name="i-lucide-minus" class="size-4" />
              </button>
              <button
                type="button"
                class="min-w-14 border-x border-[var(--site-line)] px-2 py-2 font-mono text-[0.58rem] tabular-nums text-[var(--site-ink)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_7%,transparent)]"
                aria-label="Reset to actual size"
                @click="actualSize"
              >
                {{ scaleLabel }}
              </button>
              <button
                type="button"
                class="grid size-8 place-items-center rounded-r-md text-[var(--site-muted)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_7%,transparent)] hover:text-[var(--site-ink)]"
                aria-label="Zoom in"
                @click="zoomFromCenter(1.2)"
              >
                <UIcon name="i-lucide-plus" class="size-4" />
              </button>
            </div>

            <button
              type="button"
              class="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-2 font-mono text-[0.55rem] uppercase tracking-[0.06em] text-[var(--site-muted)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_7%,transparent)] hover:text-[var(--site-ink)]"
              aria-label="Fit diagram"
              @click="fitAll"
            >
              <UIcon name="i-lucide-scan" class="size-3.5" />
              <span class="hidden sm:inline">Fit</span>
            </button>
            <button
              type="button"
              class="grid size-8 shrink-0 place-items-center rounded-md text-[var(--site-muted)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_7%,transparent)] hover:text-[var(--site-ink)]"
              aria-label="Fit width"
              title="Fit width"
              @click="fitWidth"
            >
              <UIcon name="i-lucide-unfold-horizontal" class="size-3.5" />
            </button>

            <span class="mx-1 hidden h-5 w-px bg-[var(--site-line)] sm:block" />

            <button
              type="button"
              class="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-2 font-mono text-[0.55rem] uppercase tracking-[0.06em] text-[var(--site-muted)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_7%,transparent)] hover:text-[var(--site-ink)]"
              aria-label="Download SVG"
              @click="downloadSvg"
            >
              <UIcon name="i-lucide-download" class="size-3.5" />
              <span class="hidden sm:inline">SVG</span>
            </button>
            <button
              type="button"
              class="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-2 font-mono text-[0.55rem] uppercase tracking-[0.06em] text-[var(--site-muted)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_7%,transparent)] hover:text-[var(--site-ink)]"
              aria-label="Download PNG"
              @click="downloadPng"
            >
              <UIcon name="i-lucide-image-down" class="size-3.5" />
              <span class="hidden sm:inline">PNG</span>
            </button>
            <button
              type="button"
              class="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-2 font-mono text-[0.55rem] uppercase tracking-[0.06em] text-[var(--site-muted)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_7%,transparent)] hover:text-[var(--site-ink)]"
              :aria-label="copied ? 'Copied diagram source' : 'Copy diagram source'"
              @click="copySource"
            >
              <UIcon :name="copied ? 'i-lucide-check' : 'i-lucide-copy'" class="size-3.5" />
              <span class="hidden sm:inline">{{ copied ? 'Copied' : 'Source' }}</span>
            </button>
            <span class="sr-only" aria-live="polite">{{ copied ? 'Diagram source copied' : '' }}</span>
          </div>

          <div
            ref="viewport"
            class="relative min-h-0 flex-1 cursor-grab touch-none select-none overflow-hidden bg-[var(--site-bg)] active:cursor-grabbing"
            :style="{
              backgroundImage: 'radial-gradient(circle, var(--site-grid) 1px, transparent 1px)',
              backgroundSize: '18px 18px',
            }"
            @wheel="onWheel"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerEnd"
            @pointercancel="onPointerEnd"
            @dblclick="onDoubleClick"
          >
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div
              v-if="state === 'ready'"
              class="absolute left-0 top-0 origin-top-left"
              :style="stageStyle"
              v-html="svg"
            />
            <div v-else-if="state === 'error'" class="absolute inset-0 grid place-items-center p-6">
              <div class="max-w-xl text-center">
                <p class="m-0 flex items-center justify-center gap-2 font-mono text-[0.6rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">
                  <UIcon name="i-lucide-triangle-alert" class="size-4 text-[var(--chart-orange)]" />
                  Diagram source could not be rendered
                </p>
                <pre class="mt-4 max-h-72 overflow-auto rounded-lg border border-[var(--site-line)] bg-[var(--site-code-bg)] p-4 text-left font-mono text-xs leading-relaxed text-[var(--site-ink)]"><code>{{ props.code }}</code></pre>
              </div>
            </div>
            <div v-else class="absolute inset-0 grid place-items-center">
              <div class="flex items-center gap-2 font-mono text-[0.6rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">
                <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" />
                Rendering diagram
              </div>
            </div>

            <p
              v-if="state === 'ready'"
              class="pointer-events-none absolute bottom-3 left-1/2 m-0 -translate-x-1/2 rounded-full border border-[var(--site-line)] bg-[color-mix(in_srgb,var(--site-bg)_86%,transparent)] px-3 py-1 font-mono text-[0.5rem] uppercase tracking-[0.08em] text-[var(--site-muted)] backdrop-blur"
            >
              Scroll to zoom · drag to pan
            </p>
            <p
              v-if="notice"
              class="absolute bottom-3 right-4 m-0 rounded-md border border-[var(--site-line)] bg-[var(--site-surface)] px-3 py-1.5 text-xs text-[var(--site-ink)] shadow-lg"
              role="status"
            >
              {{ notice }}
            </p>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
:deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
  max-width: none !important;
}
</style>
