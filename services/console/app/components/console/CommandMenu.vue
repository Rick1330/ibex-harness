<script setup lang="ts">
import { ArrowRight, Search } from "@lucide/vue"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { primaryNavigation } from "@/lib/navigation"

type CommandItem = {
  label: string
  to: string
  group: string
  hint: string
  preview: boolean
}

const dialog = ref<HTMLDialogElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const query = ref("")
const activeIndex = ref(0)

const allItems = computed<CommandItem[]>(() =>
  primaryNavigation.flatMap((group) =>
    group.items.map((item) => ({
      label: item.label,
      to: item.to,
      group: group.label,
      hint: item.question,
      preview: item.availability === "preview",
    })),
  ),
)

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return allItems.value
  return allItems.value.filter((item) =>
    `${item.label} ${item.group} ${item.hint}`.toLowerCase().includes(needle),
  )
})

const grouped = computed(() => {
  const groups = new Map<string, CommandItem[]>()
  for (const item of filtered.value) {
    groups.set(item.group, [...(groups.get(item.group) ?? []), item])
  }
  return [...groups.entries()]
})

function openMenu(): void {
  query.value = ""
  activeIndex.value = 0
  dialog.value?.showModal()
  void nextTick(() => input.value?.focus())
}

function closeMenu(): void {
  dialog.value?.close()
}

function select(item: CommandItem | undefined): void {
  if (!item) return
  closeMenu()
  void navigateTo(item.to)
}

function onBackdrop(event: MouseEvent): void {
  if (event.target === dialog.value) closeMenu()
}

function move(delta: number): void {
  if (!filtered.value.length) return
  activeIndex.value = (activeIndex.value + delta + filtered.value.length) % filtered.value.length
}

watch(activeIndex, async (index) => {
  await nextTick()
  dialog.value
    ?.querySelector<HTMLElement>(`[data-command-index="${index}"]`)
    ?.scrollIntoView({ block: "nearest" })
})

function onInputKeydown(event: KeyboardEvent): void {
  if (event.key === "ArrowDown") {
    event.preventDefault()
    move(1)
  } else if (event.key === "ArrowUp") {
    event.preventDefault()
    move(-1)
  } else if (event.key === "Enter") {
    event.preventDefault()
    select(filtered.value[activeIndex.value])
  }
}

function onGlobalKeydown(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault()
    openMenu()
  }
}

onMounted(() => window.addEventListener("keydown", onGlobalKeydown))
onBeforeUnmount(() => window.removeEventListener("keydown", onGlobalKeydown))

defineExpose({ open: openMenu })
</script>

<template>
  <dialog
    ref="dialog"
    class="command-dialog"
    aria-label="Search console"
    @click="onBackdrop"
    @close="query = ''"
  >
    <div class="overflow-hidden rounded-lg border border-line bg-overlay text-fg-1 shadow-[0_8px_24px_rgba(0,0,0,.4)]">
      <div class="flex items-center gap-2.5 border-b border-line-subtle px-3.5">
        <Search :size="18" :stroke-width="1.75" class="text-fg-3" aria-hidden="true" />
        <input
          ref="input"
          v-model="query"
          type="search"
          placeholder="Search pages and surfaces…"
          class="h-11 w-full bg-transparent text-sm outline-none placeholder:text-fg-3"
          aria-label="Search pages"
          autocomplete="off"
          spellcheck="false"
          @input="activeIndex = 0"
          @keydown="onInputKeydown"
        >
        <kbd class="rounded border border-line-subtle px-1.5 py-0.5 font-mono text-[0.8125rem] text-fg-3">esc</kbd>
      </div>

      <div class="max-h-[22rem] overflow-y-auto p-1.5">
        <div v-if="!filtered.length" class="px-3 py-8 text-center text-sm text-fg-3">
          No matching pages.
        </div>
        <div v-for="[group, items] in grouped" :key="group" class="py-0.5">
          <p class="ix-label px-2 py-1.5">{{ group }}</p>
          <button
            v-for="item in items"
            :key="item.to"
            :data-command-index="filtered.indexOf(item)"
            type="button"
            class="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-raised focus-visible:bg-raised focus-visible:outline-none"
            :class="filtered.indexOf(item) === activeIndex && 'bg-raised'"
            @click="select(item)"
            @mouseenter="activeIndex = filtered.indexOf(item)"
          >
            <span class="min-w-0 flex-1">
              <span class="block truncate font-medium">{{ item.label }}</span>
              <span class="mt-0.5 block truncate text-xs text-fg-3">{{ item.hint }}</span>
            </span>
            <span
              v-if="item.preview"
              class="rounded-full border border-dashed border-line-strong px-1.5 py-0.5 font-mono text-[0.75rem] text-fg-3"
            >
              Preview
            </span>
            <ArrowRight :size="15" :stroke-width="1.75" class="shrink-0 text-fg-3" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div class="flex items-center justify-between border-t border-line-subtle px-3.5 py-2 text-[0.8125rem] text-fg-3">
        <span>↑ ↓ move · Enter open</span>
        <span>{{ filtered.length }} {{ filtered.length === 1 ? "page" : "pages" }}</span>
      </div>
    </div>
  </dialog>
</template>

<style scoped>
.command-dialog {
  inset: 0;
  width: min(34rem, calc(100vw - 2rem));
  max-width: none;
  margin: auto;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
}

.command-dialog::backdrop {
  background: rgb(0 0 0 / 0.56);
}
</style>
