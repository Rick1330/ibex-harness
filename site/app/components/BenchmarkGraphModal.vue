<script setup lang="ts">
export interface ModalSummaryItem {
  label: string
  value: string
  note?: string
  color?: string
  previous?: string
  change?: string
  tone?: 'better' | 'worse' | 'same'
}

export interface ModalComparisonMetric {
  label: string
  current: string
  previous: string
  change: string
  tone: 'better' | 'worse' | 'same'
}

const props = withDefaults(defineProps<{
  open: boolean
  eyebrow?: string
  title: string
  description?: string
  sourceHref?: string
  summary?: ModalSummaryItem[]
  columns?: string[]
  rows?: string[][]
  tableNote?: string
  selectable?: boolean
  activeRow?: number
  pinnedRow?: number
  selectionLabel?: string
}>(), {
  eyebrow: '',
  description: '',
  sourceHref: '',
  summary: () => [],
  columns: () => [],
  rows: () => [],
  tableNote: '',
  selectable: false,
  activeRow: -1,
  pinnedRow: -1,
  selectionLabel: '',
})

const emit = defineEmits<{
  close: []
  preview: [row: number | null]
  select: [row: number]
}>()

const titleId = useId()
const panel = ref<HTMLElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
let restoreFocus: HTMLElement | null = null
let previousOverflow = ''

async function onOpen() {
  restoreFocus = document.activeElement as HTMLElement | null
  previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  await nextTick()
  closeButton.value?.focus()
}

function onClose() {
  document.body.style.overflow = previousOverflow
  restoreFocus?.focus()
  emit('close')
}

watch(() => props.open, (open) => {
  if (open) void onOpen()
  else document.body.style.overflow = previousOverflow
})

function onKeydown(event: KeyboardEvent) {
  if (!props.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    onClose()
    return
  }
  if (event.key !== 'Tab' || !panel.value) return

  const focusable = [...panel.value.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')]
    .filter(element => element.offsetParent !== null)
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
}

function onRowKeydown(event: KeyboardEvent, row: number) {
  if (!props.selectable) return
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  emit('select', row)
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = previousOverflow
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
        class="fixed inset-0 z-[80] flex items-end justify-center bg-black/70 p-0 backdrop-blur-sm sm:items-center sm:p-5"
        @click.self="onClose"
      >
        <div
          ref="panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          class="flex max-h-[94dvh] w-full flex-col overflow-hidden border border-[var(--site-line)] bg-[var(--site-bg)] shadow-[0_40px_120px_-30px_#000] sm:max-w-6xl sm:rounded-2xl"
        >
          <header class="flex shrink-0 items-start gap-4 border-b border-[var(--site-line)] px-5 py-4 sm:px-7 sm:py-5">
            <div class="min-w-0 flex-1">
              <p v-if="props.eyebrow" class="m-0 font-mono text-[0.55rem] uppercase tracking-[0.12em] text-[var(--site-signal)]">
                {{ props.eyebrow }}
              </p>
              <h2 :id="titleId" class="m-0 mt-1 text-xl font-medium tracking-[-0.03em] sm:text-2xl">
                {{ props.title }}
              </h2>
              <p v-if="props.description" class="m-0 mt-2 max-w-3xl text-xs leading-relaxed text-[var(--site-muted)] sm:text-sm">
                {{ props.description }}
              </p>
            </div>

            <div class="flex shrink-0 items-center gap-1">
              <a
                v-if="props.sourceHref"
                :href="props.sourceHref"
                target="_blank"
                rel="noreferrer"
                class="hidden items-center gap-1.5 rounded-md px-2.5 py-2 font-mono text-[0.54rem] uppercase tracking-[0.08em] text-[var(--site-muted)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_6%,transparent)] hover:text-[var(--site-ink)] sm:inline-flex"
              >
                Source run
                <UIcon name="i-lucide-arrow-up-right" class="size-3" />
              </a>
              <button
                ref="closeButton"
                type="button"
                class="grid size-8 place-items-center rounded-md text-[var(--site-muted)] transition-colors hover:bg-[color-mix(in_srgb,var(--site-ink)_6%,transparent)] hover:text-[var(--site-ink)]"
                aria-label="Close chart detail"
                @click="onClose"
              >
                <UIcon name="i-lucide-x" class="size-4" />
              </button>
            </div>
          </header>

          <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-4 sm:overflow-hidden sm:px-7 sm:py-5">
            <div class="shrink-0 rounded-xl border border-[var(--site-line)] bg-[color-mix(in_srgb,var(--site-surface)_76%,transparent)] px-4 py-4 sm:px-6 sm:py-5">
              <div v-if="props.selectionLabel" class="mb-3 flex flex-wrap items-center justify-between gap-2">
                <p class="m-0 font-mono text-[0.56rem] uppercase tracking-[0.08em] text-[var(--site-ink)]">
                  {{ props.selectionLabel }}
                </p>
                <p v-if="props.selectable" class="m-0 font-mono text-[0.54rem] uppercase tracking-[0.06em] text-[var(--site-muted)]">
                  Hover to preview · click to pin
                </p>
              </div>
              <slot />
            </div>

            <div v-if="props.summary.length" class="mt-3 grid shrink-0 grid-cols-2 gap-px overflow-hidden rounded-xl border border-[var(--site-line)] bg-[var(--site-line)] sm:grid-cols-4">
              <div v-for="item in props.summary" :key="item.label" class="bg-[var(--site-bg)] px-3.5 py-2.5 sm:px-4 sm:py-3">
                <p class="m-0 flex items-center gap-2 font-mono text-[0.5rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">
                  <span v-if="item.color" class="size-1.5 rounded-full" :style="{ background: item.color }" />
                  {{ item.label }}
                  <span v-if="item.note" class="tracking-normal normal-case opacity-80">{{ item.note }}</span>
                </p>
                <p class="m-0 mt-1.5 text-lg font-medium tracking-[-0.03em]">{{ item.value }}</p>
                <p v-if="item.previous && item.change && item.change !== '—'" class="m-0 mt-1 font-mono text-[0.6rem] text-[var(--site-muted)]">
                  was {{ item.previous }}
                  <span
                    :class="item.tone === 'better'
                      ? 'text-[var(--site-signal)]'
                      : item.tone === 'worse'
                        ? 'text-[var(--chart-pink)]'
                        : 'text-[var(--site-muted)]'"
                  >{{ item.change }}</span>
                </p>
              </div>
            </div>

            <div v-if="props.columns.length" class="mt-3 flex flex-col sm:min-h-0 sm:flex-1">
              <div class="min-h-0 overflow-auto overscroll-contain rounded-xl border border-[var(--site-line)] sm:max-h-[38dvh] sm:flex-1">
                <table class="w-full min-w-[56rem] border-collapse text-left text-xs">
                  <thead class="sticky top-0 z-10 bg-[color-mix(in_srgb,var(--site-surface)_92%,var(--site-bg))] font-mono text-[0.5rem] uppercase tracking-[0.1em] text-[var(--site-muted)] backdrop-blur">
                    <tr>
                      <th v-for="column in props.columns" :key="column" class="whitespace-nowrap border-b border-[var(--site-line)] px-4 py-3 font-medium first:pl-5 last:pr-5">
                        {{ column }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(row, rowIndex) in props.rows"
                      :key="rowIndex"
                      class="scroll-mt-10 border-t border-[var(--site-line)] transition-colors first:border-t-0"
                      :class="[
                        props.selectable ? 'cursor-pointer hover:bg-[color-mix(in_srgb,var(--site-ink)_4%,transparent)]' : '',
                        rowIndex === props.activeRow ? 'bg-[color-mix(in_srgb,var(--site-signal)_8%,transparent)]' : '',
                        rowIndex === props.pinnedRow && rowIndex !== props.activeRow ? 'bg-[color-mix(in_srgb,var(--site-signal)_4%,transparent)]' : '',
                      ]"
                      :tabindex="props.selectable ? 0 : undefined"
                      :aria-selected="props.selectable ? rowIndex === props.pinnedRow : undefined"
                      @mouseenter="props.selectable && emit('preview', rowIndex)"
                      @mouseleave="props.selectable && emit('preview', null)"
                      @focus="props.selectable && emit('preview', rowIndex)"
                      @blur="props.selectable && emit('preview', null)"
                      @click="props.selectable && emit('select', rowIndex)"
                      @keydown="onRowKeydown($event, rowIndex)"
                    >
                      <td
                        v-for="(cell, cellIndex) in row"
                        :key="cellIndex"
                        class="whitespace-nowrap px-4 py-2.5 font-mono tabular-nums first:pl-5 last:pr-5"
                        :class="cellIndex === 0 ? 'text-[var(--site-ink)]' : 'text-[var(--site-muted)]'"
                      >
                        {{ cell }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-if="props.tableNote" class="m-0 shrink-0 px-1 pt-2 font-mono text-[0.54rem] uppercase tracking-[0.08em] text-[var(--site-muted)]">
                {{ props.tableNote }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
