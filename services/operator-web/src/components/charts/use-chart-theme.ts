"use client"

import * as React from "react"

/**
 * Shared chart theme tokens — keep analytics / overview / drift charts
 * verbally consistent (grid from --border, mono 11px labels, panel tooltip).
 */
export type ChartTheme = {
  foreground: string
  muted: string
  border: string
  borderStrong: string
  panel: string
  destructive: string
  fontMono: string
  labelSize: number
}

export function useChartTheme(): ChartTheme {
  const [theme, setTheme] = React.useState<ChartTheme>({
    foreground: "oklch(0.145 0 0)",
    muted: "oklch(0.556 0 0)",
    border: "oklch(0.922 0 0)",
    borderStrong: "oklch(0.708 0 0)",
    panel: "oklch(1 0 0)",
    destructive: "oklch(0.577 0.245 27.325)",
    fontMono: "ui-monospace, SFMono-Regular, Menlo, monospace",
    labelSize: 11,
  })

  React.useEffect(() => {
    const styles = getComputedStyle(document.documentElement)
    const read = (name: string, fallback: string) =>
      styles.getPropertyValue(name).trim() || fallback
    setTheme({
      foreground: read("--foreground", "oklch(0.145 0 0)"),
      muted: read("--muted-foreground", "oklch(0.556 0 0)"),
      border: read("--border", "oklch(0.922 0 0)"),
      borderStrong: read("--ring", "oklch(0.708 0 0)"),
      panel: read("--card", "oklch(1 0 0)"),
      destructive: read("--destructive", "oklch(0.577 0.245 27.325)"),
      fontMono: "ui-monospace, SFMono-Regular, Menlo, monospace",
      labelSize: 11,
    })
  }, [])

  return theme
}
