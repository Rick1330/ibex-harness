import { computed } from "vue"
import { CONSOLE_DEMO_ENABLED, resolveDemoMode } from "@/lib/console-demo"

/**
 * Development fixtures are on by default only in `nuxt dev`.
 * `?demo=0` forces the fail-closed live behavior; `?demo=1` is a development
 * convenience and never enables fixtures in a production build.
 */
export function useConsoleDemo() {
  const route = useRoute()
  return computed(() => resolveDemoMode(CONSOLE_DEMO_ENABLED, route.query.demo))
}
