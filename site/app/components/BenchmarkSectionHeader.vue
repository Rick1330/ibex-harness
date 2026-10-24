<script setup lang="ts">
defineProps<{
  index: string
  label: string
  title: string
  description: string
  icon: string
  tag?: string
  runUrl?: string
  runNumber?: number
}>()
</script>

<template>
  <header class="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
    <div class="flex min-w-0 gap-4">
      <UIcon :name="icon" class="mt-1.5 size-6 shrink-0 text-[var(--site-signal)]" />

      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-x-3 gap-y-2 font-mono text-[0.6rem] uppercase tracking-[0.14em]">
          <span class="text-[var(--site-muted)]">{{ index }}</span>
          <span class="h-px w-5 bg-[var(--site-line-strong)]" />
          <span class="text-[var(--site-signal)]">{{ label }}</span>
          <span v-if="tag" class="text-[var(--site-muted)]">/ {{ tag }}</span>
        </div>

        <h2 class="site-display mt-4 max-w-3xl text-4xl sm:text-5xl lg:text-[3.4rem]">
          {{ title }}
        </h2>
        <p class="mt-4 max-w-2xl text-sm leading-relaxed text-[var(--site-muted)]">
          {{ description }}
        </p>
      </div>
    </div>

    <a
      v-if="runUrl"
      :href="runUrl"
      target="_blank"
      rel="noreferrer"
      class="inline-flex shrink-0 items-center gap-1.5 self-start font-mono text-[0.58rem] uppercase tracking-[0.1em] text-[var(--site-muted)] transition-colors hover:text-[var(--site-ink)]"
    >
      <UIcon name="i-lucide-github" class="size-3.5" />
      Run {{ runNumber }}
      <UIcon name="i-lucide-arrow-up-right" class="size-3" />
    </a>
  </header>
</template>
