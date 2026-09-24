"use client"

import * as React from "react"

type Theme = "light" | "dark" | "system"

type ThemeContextValue = {
  theme: Theme
  setTheme: (theme: Theme) => void
  resolvedTheme: "light" | "dark"
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null)

function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light"
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light"
}

function applyTheme(theme: Theme) {
  const resolved = theme === "system" ? getSystemTheme() : theme
  const root = document.documentElement
  root.classList.toggle("dark", resolved === "dark")
  root.style.colorScheme = resolved
}

/**
 * Client theme provider without injecting a <script> child (React 19 warns
 * when next-themes renders its FOUC script inside a Client Component).
 * FOUC prevention lives in root layout as a Server Component script instead.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = React.useState<Theme>("system")
  const [resolvedTheme, setResolvedTheme] = React.useState<"light" | "dark">(
    "light",
  )
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    let initial: Theme = "system"
    try {
      const stored = localStorage.getItem("theme") as Theme | null
      if (stored === "light" || stored === "dark" || stored === "system") {
        initial = stored
      }
    } catch {
      /* ignore */
    }
    setThemeState(initial)
    const resolved = initial === "system" ? getSystemTheme() : initial
    setResolvedTheme(resolved)
    applyTheme(initial)
    setMounted(true)

    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = () => {
      setThemeState((current) => {
        if (current === "system") {
          const next = getSystemTheme()
          setResolvedTheme(next)
          applyTheme("system")
        }
        return current
      })
    }
    mq.addEventListener("change", onChange)
    return () => mq.removeEventListener("change", onChange)
  }, [])

  const setTheme = React.useCallback((next: Theme) => {
    setThemeState(next)
    try {
      localStorage.setItem("theme", next)
    } catch {
      /* ignore */
    }
    const resolved = next === "system" ? getSystemTheme() : next
    setResolvedTheme(resolved)
    applyTheme(next)
  }, [])

  const value = React.useMemo(
    () => ({
      theme: mounted ? theme : "system",
      setTheme,
      resolvedTheme: mounted ? resolvedTheme : "light",
    }),
    [mounted, theme, setTheme, resolvedTheme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = React.useContext(ThemeContext)
  if (!ctx) {
    return {
      theme: "system" as Theme,
      setTheme: () => {},
      resolvedTheme: "light" as const,
    }
  }
  return ctx
}
