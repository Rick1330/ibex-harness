import { computed } from "vue"
import { CONSOLE_DEMO_ENABLED } from "@/lib/console-demo"

/**
 * Development fixtures are on by default only in `nuxt dev`.
 * `?demo=0` forces the fail-closed live behavior; `?demo=1` opts in explicitly.
 */
export function useConsoleDemo() {
  const route = useRoute()
  return computed(() => {
    const value = route.query.demo
    if (value === "0") return false
    if (value === "1") return true
    return CONSOLE_DEMO_ENABLED
  })
}
