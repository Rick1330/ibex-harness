<script setup lang="ts">
import { ref } from "vue"
import { Check, Copy, X } from "@lucide/vue"
import type { PreviewSession, SessionRound } from "@/lib/session-preview"
import MemoryJsonView from "@/components/console/memory/primitives/MemoryJsonView.vue"

const props = defineProps<{
  session: PreviewSession
  rounds: SessionRound[]
}>()

const dialog = ref<HTMLDialogElement | null>(null)
const copied = ref(false)

function open(): void {
  dialog.value?.showModal()
}

function close(): void {
  dialog.value?.close()
}

function onBackdrop(event: MouseEvent): void {
  if (event.target === dialog.value) close()
}

async function copy(): Promise<void> {
  if (!import.meta.client) return
  try {
    await navigator.clipboard.writeText(JSON.stringify({ session: props.session, rounds: props.rounds }, null, 2))
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 1_500)
  } catch {
    copied.value = false
  }
}

defineExpose({ open, close })
</script>

<template>
  <dialog ref="dialog" class="ix-sheet" aria-labelledby="session-raw-title" @click="onBackdrop">
    <div class="flex h-full flex-col">
      <header class="flex items-center justify-between gap-3 border-b border-line-subtle px-4 py-3">
        <div class="min-w-0">
          <h2 id="session-raw-title" class="text-sm font-semibold text-fg-1">Raw session record</h2>
          <p class="mt-0.5 truncate font-mono text-xs text-fg-3">{{ session.id }} · illustrative data</p>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <button
            type="button"
            class="inline-flex h-7 items-center gap-1.5 rounded-md border border-line-subtle px-2 text-xs text-fg-2 transition-colors hover:border-line-strong hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            @click="copy"
          >
            <Check v-if="copied" :size="12" :stroke-width="2" class="text-ok" aria-hidden="true" />
            <Copy v-else :size="12" :stroke-width="1.75" aria-hidden="true" />
            {{ copied ? "Copied" : "Copy" }}
          </button>
          <button
            type="button"
            class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
            aria-label="Close raw session record"
            @click="close"
          >
            <X :size="15" :stroke-width="1.75" aria-hidden="true" />
          </button>
        </div>
      </header>

      <div class="min-h-0 flex-1 overflow-auto p-4">
        <MemoryJsonView :value="{ session, rounds }" />
      </div>

      <footer class="border-t border-line-subtle px-4 py-2.5 text-[0.6875rem] leading-4 text-fg-3">
        Fixture values only. Nothing here was read from a live service.
      </footer>
    </div>
  </dialog>
</template>

<style scoped>
.ix-sheet {
  width: min(64rem, calc(100vw - 2rem));
  max-width: none;
  height: min(48rem, calc(100dvh - 2rem));
  max-height: none;
  margin: auto;
  border: 1px solid var(--ix-line);
  border-radius: 12px;
  background: var(--ix-overlay);
  padding: 0;
  color: var(--ix-fg-1);
}

.ix-sheet[open] {
  display: flex;
  flex-direction: column;
}

.ix-sheet::backdrop {
  background: rgb(0 0 0 / 0.55);
}

@media (max-width: 640px) {
  .ix-sheet {
    width: 100vw;
    height: 100dvh;
    border: 0;
    border-radius: 0;
  }
}
</style>
