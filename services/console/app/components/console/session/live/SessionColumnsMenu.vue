<script setup lang="ts">
import { nextTick, ref } from "vue"
import { onClickOutside } from "@vueuse/core"
import { Check, Columns3 } from "@lucide/vue"
import {
  SESSION_OPTIONAL_COLUMNS,
  sessionColumnVisible,
  toggleSessionColumn,
  type SessionColumnId,
} from "@/lib/session-list"

const props = defineProps<{ modelValue: SessionColumnId[] }>()
const emit = defineEmits<{ "update:modelValue": [value: SessionColumnId[]] }>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)

onClickOutside(root, () => {
  open.value = false
})

/**
 * Closing with `v-if` removes the focused switch (or the panel itself) from the
 * DOM, so focus would fall back to `document.body` and a keyboard user would
 * lose their place. Escape is a dismissal and returns focus to the trigger;
 * a click outside is not, and leaves focus wherever the reader put it.
 */
async function dismissMenu(): Promise<void> {
  if (!open.value) return
  open.value = false
  await nextTick()
  trigger.value?.focus()
}

function toggle(id: SessionColumnId): void {
  emit("update:modelValue", toggleSessionColumn(props.modelValue, id))
}
</script>

<template>
  <div ref="root" class="relative" @keydown.esc.stop.prevent="dismissMenu">
    <button
      ref="trigger"
      type="button"
      class="ix-button-secondary"
      :aria-expanded="open"
      :aria-controls="open ? 'session-columns' : undefined"
      @click="open = !open"
    >
      <Columns3 :size="13" :stroke-width="2" aria-hidden="true" />
      Columns
    </button>

    <div
      v-if="open"
      id="session-columns"
      role="group"
      aria-label="Optional table columns"
      class="absolute right-0 z-20 mt-1 w-52 rounded-lg border border-line bg-surface p-1.5 shadow-lg"
    >
      <p class="ix-label px-1.5 pt-1 pb-1.5">Optional columns</p>
      <button
        v-for="column in SESSION_OPTIONAL_COLUMNS"
        :key="column.id"
        type="button"
        role="switch"
        :aria-checked="sessionColumnVisible(modelValue, column.id)"
        class="flex w-full items-center justify-between gap-2 rounded px-1.5 py-1.5 text-xs text-fg-2 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
        @click="toggle(column.id)"
      >
        {{ column.label }}
        <Check
          v-if="sessionColumnVisible(modelValue, column.id)"
          :size="12"
          :stroke-width="2.2"
          class="text-ok"
          aria-hidden="true"
        />
        <span v-else class="size-3" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>
