<script setup lang="ts">
import { ref } from "vue"
import { X } from "@lucide/vue"

const dialog = ref<HTMLDialogElement | null>(null)

const groups = [
  {
    label: "Navigate",
    items: [
      { keys: ["J"], label: "Next turn" },
      { keys: ["K"], label: "Previous turn" },
      { keys: ["1"], label: "Trace tab" },
      { keys: ["2"], label: "Memories tab" },
      { keys: ["3"], label: "Directive tab" },
      { keys: ["4"], label: "Policy tab" },
      { keys: ["5"], label: "Drift tab" },
      { keys: ["6"], label: "Privacy tab" },
    ],
  },
  {
    label: "Panels",
    items: [
      { keys: ["←", "→"], label: "Move between tabs when the tab bar has focus" },
      { keys: ["["], label: "Collapse or expand the outline" },
      { keys: ["]"], label: "Collapse or expand the inspector" },
      { keys: ["↑", "↓"], label: "Move through spans in the Trace tab" },
      { keys: ["E"], label: "Expand all steps in the selected turn" },
    ],
  },
  {
    label: "Help",
    items: [{ keys: ["?"], label: "Open or close this shortcut sheet" }],
  },
]

function open(): void {
  dialog.value?.showModal()
}

function close(): void {
  dialog.value?.close()
}

function toggle(): void {
  if (dialog.value?.open) close()
  else open()
}

function onBackdrop(event: MouseEvent): void {
  if (event.target === dialog.value) close()
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    event.preventDefault()
    close()
  }
}

defineExpose({ open, close, toggle })
</script>

<template>
  <dialog ref="dialog" class="ix-sheet ix-sheet-shortcuts" aria-labelledby="session-shortcuts-title" @click="onBackdrop" @keydown="onKeydown">
    <div class="flex h-full flex-col">
      <header class="flex items-center justify-between gap-3 border-b border-line-subtle px-4 py-3">
        <div>
          <h2 id="session-shortcuts-title" class="text-sm font-semibold text-fg-1">Keyboard shortcuts</h2>
          <p class="mt-0.5 text-xs text-fg-3">Session transcript and inspector</p>
        </div>
        <button
          type="button"
          class="inline-flex size-7 items-center justify-center rounded-md text-fg-3 transition-colors hover:bg-raised hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
          aria-label="Close keyboard shortcuts"
          @click="close"
        >
          <X :size="15" :stroke-width="1.75" aria-hidden="true" />
        </button>
      </header>

      <div class="min-h-0 flex-1 overflow-y-auto p-4">
        <section v-for="group in groups" :key="group.label" class="mb-5 last:mb-0">
          <h3 class="mb-2 text-[0.625rem] font-semibold tracking-[0.1em] text-fg-3 uppercase">{{ group.label }}</h3>
          <dl class="divide-y divide-line-subtle">
            <div v-for="item in group.items" :key="item.label" class="flex items-center justify-between gap-4 py-2">
              <dt class="text-[0.8125rem] leading-5 text-fg-2">{{ item.label }}</dt>
              <dd class="flex shrink-0 items-center gap-1">
                <kbd v-for="key in item.keys" :key="key" class="ix-kbd">{{ key }}</kbd>
              </dd>
            </div>
          </dl>
        </section>
      </div>

      <footer class="border-t border-line-subtle px-4 py-2.5 text-[0.6875rem] leading-4 text-fg-3">
        Shortcuts are ignored while typing in a field.
      </footer>
    </div>
  </dialog>
</template>

<style scoped>
.ix-sheet {
  width: min(34rem, calc(100vw - 2rem));
  max-width: none;
  height: min(34rem, calc(100dvh - 2rem));
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

.ix-kbd {
  display: inline-flex;
  min-width: 1.375rem;
  height: 1.375rem;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ix-line);
  border-radius: 4px;
  background: var(--ix-surface);
  padding: 0 0.3125rem;
  font-family: var(--font-mono);
  font-size: 0.625rem;
  line-height: 1;
  color: var(--ix-fg-2);
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
