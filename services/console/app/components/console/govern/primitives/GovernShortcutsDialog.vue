<script setup lang="ts">
import { ref, watch } from "vue"
import { X } from "@lucide/vue"

export type ShortcutRow = { keys: string; label: string }
export type ShortcutGroup = { title: string; rows: ShortcutRow[] }

const props = withDefaults(
  defineProps<{
    open: boolean
    groups: ShortcutGroup[]
  }>(),
  {},
)

const emit = defineEmits<{ "update:open": [open: boolean] }>()

const dialog = ref<HTMLDialogElement | null>(null)

watch(
  () => props.open,
  (open) => {
    const element = dialog.value
    if (!element) return
    if (open && !element.open) element.showModal()
    else if (!open && element.open) element.close()
  },
)

function close(): void {
  emit("update:open", false)
}

function onBackdrop(event: MouseEvent): void {
  if (event.target === dialog.value) close()
}
</script>

<template>
  <dialog
    ref="dialog"
    class="fixed inset-0 z-50 m-auto w-[min(38rem,calc(100vw-2rem))] rounded-lg border border-line bg-overlay p-0 text-fg-1 shadow-2xl backdrop:bg-black/55"
    aria-labelledby="govern-shortcuts-title"
    @click="onBackdrop"
    @cancel.prevent="close"
  >
    <div class="flex items-center justify-between border-b border-line-subtle px-4 py-2.5">
      <h2 id="govern-shortcuts-title" class="text-sm font-semibold">Keyboard shortcuts</h2>
      <button
        type="button"
        class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        aria-label="Close shortcuts"
        @click="close"
      >
        <X :size="15" :stroke-width="1.9" aria-hidden="true" />
      </button>
    </div>
    <div class="grid gap-x-6 gap-y-4 px-4 py-3 sm:grid-cols-2">
      <section v-for="group in groups" :key="group.title" class="min-w-0">
        <h3 class="text-[0.6875rem] font-semibold tracking-[0.08em] text-fg-3 uppercase">{{ group.title }}</h3>
        <dl class="mt-1.5 space-y-1">
          <div v-for="row in group.rows" :key="row.keys" class="flex items-baseline justify-between gap-4 text-xs leading-5">
            <dt class="text-fg-2">{{ row.label }}</dt>
            <dd class="shrink-0 font-mono text-[0.6875rem] text-fg-3">{{ row.keys }}</dd>
          </div>
        </dl>
      </section>
    </div>
    <p class="border-t border-line-subtle px-4 py-2 text-[0.6875rem] leading-4 text-fg-3">
      Shortcuts are ignored while typing in a field. Press Escape to close this sheet.
    </p>
  </dialog>
</template>
