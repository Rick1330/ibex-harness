import { ref, watch, type Ref } from "vue"
import { useRoute, useRouter } from "vue-router"

/**
 * A tab-local filter stored in the URL so a deep link restores the exact view.
 * Writes use `replace` and debounce text input, keeping the back stack clean
 * while still surviving reload and back/forward navigation between pages.
 */
export function useAgentTabQueryString(key: string, options: { delay?: number } = {}): Ref<string> {
  const route = useRoute()
  const router = useRouter()
  const read = (): string => (typeof route.query[key] === "string" ? String(route.query[key]) : "")
  const state = ref(read())
  let timer: ReturnType<typeof setTimeout> | null = null

  function commit(): void {
    if (!import.meta.client) return
    if (read() === state.value) return
    const next = { ...route.query } as Record<string, string | string[] | undefined>
    if (state.value.trim()) next[key] = state.value
    else Reflect.deleteProperty(next, key)
    void router.replace({ query: next }).catch(() => undefined)
  }

  watch(state, () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(commit, options.delay ?? 180)
  })

  watch(
    () => route.query[key],
    () => {
      const next = read()
      if (next !== state.value) state.value = next
    },
  )

  return state
}

export function useAgentTabQueryBoolean(key: string): Ref<boolean> {
  const route = useRoute()
  const router = useRouter()
  const read = (): boolean => route.query[key] === "1"
  const state = ref(read())

  watch(state, (value) => {
    if (!import.meta.client) return
    if (read() === value) return
    const next = { ...route.query } as Record<string, string | string[] | undefined>
    if (value) next[key] = "1"
    else Reflect.deleteProperty(next, key)
    void router.replace({ query: next }).catch(() => undefined)
  })

  watch(
    () => route.query[key],
    () => {
      const next = read()
      if (next !== state.value) state.value = next
    },
  )

  return state
}
