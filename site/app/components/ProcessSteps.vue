<script setup lang="ts">
interface Step {
  title: string
  description?: string
}

defineProps<{
  steps: Step[]
}>()
</script>

<template>
  <ol class="my-6 grid gap-px overflow-hidden border border-[var(--site-line)] bg-[var(--site-line)]">
    <li
      v-for="(step, index) in steps"
      :key="step.title"
      class="grid gap-2 bg-[var(--site-surface)] p-4 sm:grid-cols-[3rem_1fr]"
    >
      <span class="site-mono text-[0.68rem] tracking-[0.12em] text-[var(--site-muted)]">
        {{ String(index + 1).padStart(2, '0') }}
      </span>
      <div>
        <p class="m-0 font-medium tracking-[-0.01em] text-[var(--site-ink)]">{{ step.title }}</p>
        <p v-if="step.description" class="mt-1 text-sm leading-relaxed text-[var(--site-muted)]">
          {{ step.description }}
        </p>
      </div>
    </li>
  </ol>
</template>
