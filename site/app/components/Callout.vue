<script setup lang="ts">
defineOptions({ name: 'SiteCallout' })

const props = withDefaults(defineProps<{
  type?: 'info' | 'note' | 'tip' | 'warning' | 'danger' | 'caution' | 'success'
  title?: string
  to?: string
}>(), {
  type: 'info',
  title: '',
  to: '',
})

const icon = computed(() => ({
  info: 'i-lucide-info',
  note: 'i-lucide-file-text',
  tip: 'i-lucide-lightbulb',
  warning: 'i-lucide-triangle-alert',
  danger: 'i-lucide-octagon-alert',
  caution: 'i-lucide-triangle-alert',
  success: 'i-lucide-circle-check',
}[props.type]))

const tone = computed(() => ({
  info: 'border-l-[var(--color-ice)] bg-[color-mix(in_srgb,var(--color-ice)_7%,transparent)]',
  note: 'border-l-[var(--site-line-strong)] bg-[var(--site-surface)]',
  tip: 'border-l-[var(--site-signal)] bg-[color-mix(in_srgb,var(--site-signal)_7%,transparent)]',
  warning: 'border-l-[var(--color-amber)] bg-[color-mix(in_srgb,var(--color-amber)_8%,transparent)]',
  danger: 'border-l-[#d64545] bg-[color-mix(in_srgb,#d64545_8%,transparent)]',
  caution: 'border-l-[var(--color-amber)] bg-[color-mix(in_srgb,var(--color-amber)_8%,transparent)]',
  success: 'border-l-[#4d7c00] bg-[color-mix(in_srgb,#4d7c00_8%,transparent)]',
}[props.type]))
</script>

<template>
  <div class="my-6 border border-l-2 border-[var(--site-line)] px-4 py-3.5" :class="tone">
    <div class="mb-1.5 flex items-center gap-2">
      <UIcon :name="icon" class="size-4 shrink-0" />
      <p class="site-mono m-0 text-[0.68rem] font-semibold uppercase tracking-[0.12em]">
        {{ title || type }}
      </p>
    </div>
    <div class="site-prose text-sm leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <slot />
    </div>
    <NuxtLink v-if="to" :to="to" class="site-link mt-2 inline-block text-sm">
      Read more
    </NuxtLink>
  </div>
</template>
