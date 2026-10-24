<script setup lang="ts">
import { formatNumber } from '~/data/benchmarks'

export interface MicrobenchItem {
  label: string
  value: number
  display: string
  note?: string
  color?: string
  low?: number
  high?: number
}

const props = withDefaults(defineProps<{
  items: MicrobenchItem[]
  compact?: boolean
}>(), {
  compact: false,
})

const domain = computed(() => {
  const values = props.items
    .flatMap(item => [item.value, item.low ?? item.value, item.high ?? item.value])
    .filter(value => Number.isFinite(value) && value > 0)
  if (!values.length) return { min: 1, max: 10 }
  const low = 10 ** Math.floor(Math.log10(Math.min(...values)))
  const high = 10 ** Math.ceil(Math.log10(Math.max(...values)))
  return { min: low, max: high > low ? high : low * 10 }
})

const logMin = computed(() => Math.log10(domain.value.min))
const logSpan = computed(() => Math.max(Math.log10(domain.value.max) - logMin.value, 1))

function offset(value?: number) {
  if (value === undefined || !Number.isFinite(value) || value <= 0) return 0
  const ratio = (Math.log10(value) - logMin.value) / logSpan.value
  return Math.min(100, Math.max(0, ratio * 100))
}

function barWidth(value: number) {
  return Math.max(offset(value), 0.6)
}

function ciLeft(item: MicrobenchItem) {
  if (item.low === undefined) return 0
  return (offset(item.low) / barWidth(item.value)) * 100
}

function ciWidth(item: MicrobenchItem) {
  if (item.low === undefined || item.high === undefined) return 0
  return ((offset(item.high) - offset(item.low)) / barWidth(item.value)) * 100
}

const ticks = computed(() => {
  const low = Math.round(logMin.value)
  const high = Math.round(logMin.value + logSpan.value)
  const all: { value: number, left: number }[] = []
  for (let exponent = low; exponent <= high; exponent += 1) {
    const value = 10 ** exponent
    all.push({ value, left: offset(value) })
  }
  const visible = props.compact
    ? all.filter((_, index) => index % 2 === 0 || index === all.length - 1)
    : all
  return visible.map((tick, index) => ({
    ...tick,
    align: tickAlign(index, visible.length),
  }))
})

function tickAlign(index: number, count: number): 'start' | 'end' | 'center' {
  if (index === 0) return 'start'
  if (index === count - 1) return 'end'
  return 'center'
}

function tickLabel(value: number) {
  if (value >= 1_000_000) return `${formatNumber(value / 1_000_000, 0)} ms`
  if (value >= 1_000) return `${formatNumber(value / 1_000, 0)} µs`
  return `${formatNumber(value, 0)} ns`
}

function ciLabel(item: MicrobenchItem) {
  if (item.low === undefined || item.high === undefined) return ''
  return `95% CI ${formatNumber(item.low, 0)}–${formatNumber(item.high, 0)} ns`
}
</script>

<template>
  <div class="bench-micro w-full" :class="props.compact ? 'bench-micro--compact' : ''">
    <div class="bench-micro__axis" aria-hidden="true">
      <span class="bench-micro__axis-label">ns/op</span>
      <div class="bench-micro__axis-track">
        <span
          v-for="tick in ticks"
          :key="tick.value"
          class="bench-micro__tick"
          :class="`is-${tick.align}`"
          :style="{ left: `${tick.left}%` }"
        >
          {{ tickLabel(tick.value) }}
        </span>
      </div>
      <span />
    </div>

    <div
      v-for="item in props.items"
      :key="item.label"
      class="bench-micro__row"
    >
      <span class="bench-micro__label" :title="item.label">{{ item.label }}</span>
      <div class="bench-micro__track">
        <span
          v-for="tick in ticks"
          :key="`grid-${tick.value}`"
          class="bench-micro__grid"
          :style="{ left: `${tick.left}%` }"
        />
        <span
          class="bench-micro__bar"
          :style="{ width: `${barWidth(item.value)}%`, background: item.color ?? 'var(--chart-lime)' }"
        >
          <span
            v-if="item.low !== undefined && item.high !== undefined"
            class="bench-micro__ci"
            :style="{ left: `${ciLeft(item)}%`, width: `${ciWidth(item)}%` }"
            :title="ciLabel(item)"
          />
        </span>
      </div>
      <span class="bench-micro__value">
        <span class="bench-micro__number">{{ item.display }}</span>
        <span v-if="item.note" class="bench-micro__note">{{ item.note }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.bench-micro__axis {
  display: grid;
  grid-template-columns: minmax(9rem, 13rem) minmax(0, 1fr) auto;
  align-items: end;
  gap: 1rem;
  padding-bottom: 0.4rem;
}

.bench-micro__axis-label {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.52rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--site-muted);
}

.bench-micro__axis-track {
  position: relative;
  height: 1.1rem;
}

.bench-micro__tick {
  position: absolute;
  bottom: 0;
  transform: translateX(-50%);
  white-space: nowrap;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.52rem;
  color: var(--site-muted);
}

.bench-micro__tick.is-start { transform: none; }
.bench-micro__tick.is-end { transform: translateX(-100%); }

.bench-micro__row {
  display: grid;
  grid-template-columns: minmax(9rem, 13rem) minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.35rem 1rem;
  padding: 0.44rem 0;
  border-top: 1px solid var(--site-line);
}

.bench-micro__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.72rem;
  color: var(--site-ink);
}

.bench-micro__track {
  position: relative;
  height: 0.5rem;
  border-radius: 999px;
  background: var(--site-code-bg);
}

.bench-micro__grid {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: color-mix(in srgb, var(--site-line-strong) 55%, transparent);
}

.bench-micro__bar {
  position: absolute;
  inset-block: 0;
  left: 0;
  border-radius: 999px;
}

.bench-micro__ci {
  position: absolute;
  top: -0.28rem;
  bottom: -0.28rem;
  min-width: 1px;
  background: color-mix(in srgb, var(--site-bg) 62%, transparent);
}

.bench-micro__ci::before,
.bench-micro__ci::after {
  position: absolute;
  left: -2px;
  width: 5px;
  height: 1px;
  background: inherit;
  content: "";
}

.bench-micro__ci::before { top: 0; }
.bench-micro__ci::after { bottom: 0; }

.bench-micro__value {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.1rem;
  text-align: right;
}

.bench-micro__number {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.68rem;
  font-variant-numeric: tabular-nums;
  color: var(--site-ink);
}

.bench-micro__note {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.52rem;
  color: var(--site-muted);
}

@media (max-width: 640px) {
  .bench-micro__axis {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .bench-micro__axis-label { display: none; }
  .bench-micro__axis-track { grid-column: 1; }

  .bench-micro__row {
    grid-template-columns: minmax(0, 1fr) auto;
    padding: 0.4rem 0 0.55rem;
  }

  .bench-micro__track {
    grid-column: 1 / -1;
    grid-row: 2;
  }

  .bench-micro--compact .bench-micro__note { display: none; }
}
</style>
