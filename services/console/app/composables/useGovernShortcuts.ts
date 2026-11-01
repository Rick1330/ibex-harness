import { onBeforeUnmount, onMounted, ref } from "vue"

type ShortcutHandlers = Record<string, (() => void) | undefined>

const GOVERN_ROUTES: Record<string, string> = {
  p: "/policies",
  d: "/drift",
  a: "/audit",
  e: "/evidence",
  b: "/budgets",
  n: "/analytics",
  x: "/explore",
}

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest("input, textarea, select, [contenteditable]"))
}

/**
 * Shared keyboard layer for the govern surfaces.
 *
 * Handles the global `?` sheet, the `g` chord (g then p/d/a/e/b/n/x), `/` focus and
 * per-page single-key handlers. Per-page handlers win over the chord.
 */
export function useGovernShortcuts(options: {
  /** Extra single-key handlers, e.g. { j: () => move(1) }. */
  keys?: ShortcutHandlers
  /** Focus target for `/`. */
  onSearch?: () => void
  /** Called for Escape when nothing else consumed it. */
  onEscape?: () => void
}) {
  const helpOpen = ref(false)
  let chord = false
  let chordTimer: ReturnType<typeof setTimeout> | null = null

  function cancelChord(): void {
    chord = false
    if (chordTimer) {
      clearTimeout(chordTimer)
      chordTimer = null
    }
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.metaKey || event.ctrlKey || event.altKey) return
    if (isTypingTarget(event.target)) {
      if (event.key === "Escape" && options.onEscape) options.onEscape()
      return
    }

    if (chord) {
      cancelChord()
      const path = GOVERN_ROUTES[event.key.toLowerCase()]
      if (path) {
        event.preventDefault()
        void navigateTo(path)
        return
      }
    }

    if (event.key === "g" || event.key === "G") {
      event.preventDefault()
      chord = true
      chordTimer = setTimeout(cancelChord, 1_200)
      return
    }

    if (event.key === "?") {
      event.preventDefault()
      helpOpen.value = true
      return
    }

    if (event.key === "/" && options.onSearch) {
      event.preventDefault()
      options.onSearch()
      return
    }

    if (event.key === "Escape") {
      if (helpOpen.value) {
        helpOpen.value = false
        return
      }
      if (options.onEscape) {
        event.preventDefault()
        options.onEscape()
      }
      return
    }

    const handler = options.keys?.[event.key.toLowerCase()]
    if (handler && !(event.key === " " && event.target !== document.body && event.target !== document.documentElement)) {
      event.preventDefault()
      handler()
    }
  }

  onMounted(() => window.addEventListener("keydown", onKeydown))
  onBeforeUnmount(() => {
    window.removeEventListener("keydown", onKeydown)
    cancelChord()
  })

  return { helpOpen }
}
