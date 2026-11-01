import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from "vue"

type TriageRow = { id: string }

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest("input, textarea, select, [contenteditable]"))
}

/**
 * Shared keyboard triage for govern list tables: j/k moves the selection,
 * Enter opens the row page and Space opens the 480px peek drawer.
 */
export function useTriageTable<T extends TriageRow>(options: {
  rows: Ref<T[]>
  onOpen: (row: T) => void
  onPeek?: (row: T) => void
  enabled?: () => boolean
}) {
  const selectedIndex = ref(-1)
  const selectedId = computed(() => options.rows.value[selectedIndex.value]?.id ?? null)

  function select(id: string | null): void {
    selectedIndex.value = id === null ? -1 : options.rows.value.findIndex((row) => row.id === id)
  }

  function focusRow(id: string): void {
    if (!import.meta.client) return
    document.querySelector<HTMLElement>(`[data-triage-row="${id}"]`)?.focus()
  }

  function move(delta: number): void {
    const rows = options.rows.value
    if (!rows.length) return
    const next = selectedIndex.value < 0 ? (delta > 0 ? 0 : rows.length - 1) : (selectedIndex.value + delta + rows.length) % rows.length
    selectedIndex.value = next
    focusRow(rows[next]!.id)
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (options.enabled && !options.enabled()) return
    if (event.metaKey || event.ctrlKey || event.altKey) return
    if (isTypingTarget(event.target)) return
    const rows = options.rows.value
    if (!rows.length) return

    if (event.key === "j" || event.key === "J") {
      event.preventDefault()
      move(1)
      return
    }
    if (event.key === "k" || event.key === "K") {
      event.preventDefault()
      move(-1)
      return
    }

    const current = rows[selectedIndex.value]
    if (!current) return
    const onBody =
      event.target === document.body ||
      event.target === document.documentElement ||
      (event.target instanceof HTMLElement && event.target.dataset.triageRow === current.id)
    if (event.key === "Enter" && onBody) {
      event.preventDefault()
      options.onOpen(current)
    } else if (event.key === " " && options.onPeek && onBody) {
      event.preventDefault()
      options.onPeek(current)
    }
  }

  watch(
    () => options.rows.value.map((row) => row.id).join("|"),
    () => {
      if (selectedIndex.value >= options.rows.value.length) selectedIndex.value = options.rows.value.length - 1
    },
  )

  onMounted(() => window.addEventListener("keydown", handleKeydown))
  onBeforeUnmount(() => window.removeEventListener("keydown", handleKeydown))

  function rowAttrs(row: T) {
    return {
      "data-triage-row": row.id,
      "data-selected": selectedId.value === row.id ? "true" : undefined,
      tabindex: 0,
      onClick: () => options.onOpen(row),
      onFocus: () => select(row.id),
    }
  }

  return { selectedIndex, selectedId, select, move, rowAttrs, handleKeydown }
}
