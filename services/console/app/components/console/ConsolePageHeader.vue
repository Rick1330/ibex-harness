<script setup lang="ts">
import { ref } from "vue"
import GovernAboutPopover from "@/components/console/govern/primitives/GovernAboutPopover.vue"
import GovernDataSourceChip from "@/components/console/govern/primitives/GovernDataSourceChip.vue"

type DataState = "live" | "partial" | "illustrative"

type AboutNote = { lead: string; body: string }

const props = withDefaults(
  defineProps<{
    title: string
    state?: DataState
    verdict: string
    contract: string
    scope: string
    range: string
    coverage?: string
    observed?: string | null
    request?: string | null
    notes?: AboutNote[]
    crossLink?: { text: string; href: string; label: string } | null
  }>(),
  {
    state: "illustrative",
    coverage: "",
    observed: undefined,
    request: undefined,
    notes: () => [],
    crossLink: null,
  },
)

const about = ref<InstanceType<typeof GovernAboutPopover> | null>(null)

function openAbout(): void {
  about.value?.open()
}

defineExpose({ openAbout })
</script>

<template>
  <header class="flex flex-col gap-3">
    <div class="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div class="min-w-0 flex-1">
        <slot name="back" />
        <slot name="eyebrow" />
        <h1 class="ix-page-title max-w-3xl text-balance break-words text-fg-1">
          {{ props.title }}
        </h1>
        <p v-if="crossLink" class="mt-1 text-xs leading-5 text-fg-3">
          {{ crossLink.text }}
          <NuxtLink :to="crossLink.href" class="ix-link font-medium">{{ crossLink.label }}</NuxtLink>
        </p>
      </div>

      <div class="flex shrink-0 flex-wrap items-center gap-2 max-sm:w-full">
        <GovernDataSourceChip :state="state" @open="openAbout" />
        <GovernAboutPopover
          ref="about"
          :state="state"
          :verdict="verdict"
          :contract="contract"
          :scope="scope"
          :range="range"
          :coverage="coverage"
          :observed="observed"
          :request="request"
          :notes="notes"
        />
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </header>
</template>
