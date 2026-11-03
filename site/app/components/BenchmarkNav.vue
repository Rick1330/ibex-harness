<script setup lang="ts">
interface NavSuite {
  index: string
  title: string
  shortTitle: string
  icon: string
  metric?: string
  metricLabel?: string
  runs?: number
  href: string
}

const props = defineProps<{
  suites: NavSuite[]
  active: string
}>()

const utilityLinks: NavSuite[] = [
  { index: '06', title: 'Method', shortTitle: 'Method', icon: 'i-lucide-book-open', href: '#method' },
  { index: '07', title: 'Raw data', shortTitle: 'Data', icon: 'i-lucide-braces', href: '#raw-data' },
]

const items = computed<NavSuite[]>(() => [...props.suites, ...utilityLinks])

function isActive(item: NavSuite) {
  return props.active === item.href.slice(1)
}
</script>

<template>
  <nav aria-label="Benchmark suites">
    <div class="flex items-center justify-between gap-3 px-3 pb-4">
      <span class="flex items-center gap-2 font-mono text-[0.56rem] uppercase tracking-[0.14em] text-[var(--site-muted)]">
        <UIcon name="i-lucide-activity" class="size-3.5 text-[var(--site-signal)]" />
        Performance
      </span>
      <span class="site-mono text-[0.52rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">5 suites</span>
    </div>

    <div class="space-y-0.5">
      <a
        v-for="item in items"
        :key="item.href"
        :href="item.href"
        :aria-current="isActive(item) ? 'true' : undefined"
        class="group flex items-center gap-3 rounded-lg px-3 py-2 text-[0.86rem] transition-colors"
        :class="isActive(item)
          ? 'bg-[color-mix(in_srgb,var(--site-signal)_9%,transparent)] text-[var(--site-ink)]'
          : 'text-[var(--site-muted)] hover:bg-[color-mix(in_srgb,var(--site-ink)_4%,transparent)] hover:text-[var(--site-ink)]'"
      >
        <UIcon
          :name="item.icon"
          class="size-4 shrink-0 transition-colors"
          :class="isActive(item) ? 'text-[var(--site-signal)]' : 'text-[var(--site-muted)] group-hover:text-[var(--site-ink)]'"
        />
        <span class="min-w-0 truncate">{{ item.title }}</span>
      </a>
    </div>
  </nav>
</template>
