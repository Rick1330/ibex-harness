<script setup lang="ts">
import { ArrowUpRight } from "@lucide/vue"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"

withDefaults(
  defineProps<{
    open: boolean
    title: string
    description?: string
    href?: string | null
    hrefLabel?: string
  }>(),
  { description: undefined, href: null, hrefLabel: "Open full page" },
)

const emit = defineEmits<{ "update:open": [open: boolean] }>()
</script>

<template>
  <Sheet :open="open" @update:open="emit('update:open', $event)">
    <SheetContent side="right" class="w-[min(30rem,100vw)] overflow-y-auto sm:max-w-[30rem]">
      <SheetHeader class="gap-1 border-b border-line-subtle pb-3">
        <SheetTitle class="text-base leading-6">{{ title }}</SheetTitle>
        <SheetDescription v-if="description" class="text-xs leading-4 text-fg-3">{{ description }}</SheetDescription>
        <NuxtLink
          v-if="href"
          :to="href"
          class="mt-1 inline-flex w-fit items-center gap-1 text-xs font-medium text-fg-2 underline decoration-line-strong underline-offset-3 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        >
          {{ hrefLabel }}
          <ArrowUpRight :size="12" :stroke-width="1.9" aria-hidden="true" />
        </NuxtLink>
      </SheetHeader>
      <div class="mt-3 min-w-0">
        <slot />
      </div>
    </SheetContent>
  </Sheet>
</template>
