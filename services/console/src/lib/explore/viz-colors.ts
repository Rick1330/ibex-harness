/**
 * Categorical colors for Trace Inspector bars / flame / composite.
 * Distinct hues (not near-gray chart tokens) so stacked segments stay readable.
 */

export type VizTone =
  | "root"
  | "auth"
  | "context"
  | "provider"
  | "tool"
  | "stream"
  | "eval"
  | "score-a"
  | "score-b"
  | "score-c"
  | "score-d"
  | "score-e"

/** Fill + readable label text for that fill. */
export const VIZ: Record<
  VizTone,
  { fill: string; text: string; swatch: string; label: string }
> = {
  root: {
    fill: "bg-[oklch(0.28_0.02_250)] dark:bg-[oklch(0.88_0.01_250)]",
    text: "text-[oklch(0.98_0_0)] dark:text-[oklch(0.18_0_0)]",
    swatch: "bg-[oklch(0.28_0.02_250)] dark:bg-[oklch(0.88_0.01_250)]",
    label: "root",
  },
  auth: {
    fill: "bg-[oklch(0.48_0.06_250)] dark:bg-[oklch(0.68_0.07_250)]",
    text: "text-white",
    swatch: "bg-[oklch(0.48_0.06_250)] dark:bg-[oklch(0.68_0.07_250)]",
    label: "auth / gate",
  },
  context: {
    fill: "bg-[oklch(0.52_0.1_185)] dark:bg-[oklch(0.7_0.1_185)]",
    text: "text-white dark:text-[oklch(0.15_0.02_185)]",
    swatch: "bg-[oklch(0.52_0.1_185)] dark:bg-[oklch(0.7_0.1_185)]",
    label: "context",
  },
  provider: {
    fill: "bg-[oklch(0.62_0.14_55)] dark:bg-[oklch(0.76_0.12_55)]",
    text: "text-[oklch(0.2_0.04_55)]",
    swatch: "bg-[oklch(0.62_0.14_55)] dark:bg-[oklch(0.76_0.12_55)]",
    label: "provider",
  },
  tool: {
    fill: "bg-[oklch(0.55_0.14_25)] dark:bg-[oklch(0.7_0.12_25)]",
    text: "text-white",
    swatch: "bg-[oklch(0.55_0.14_25)] dark:bg-[oklch(0.7_0.12_25)]",
    label: "tool",
  },
  stream: {
    fill: "bg-[oklch(0.5_0.1_145)] dark:bg-[oklch(0.68_0.1_145)]",
    text: "text-white dark:text-[oklch(0.15_0.03_145)]",
    swatch: "bg-[oklch(0.5_0.1_145)] dark:bg-[oklch(0.68_0.1_145)]",
    label: "stream",
  },
  eval: {
    fill: "bg-[oklch(0.48_0.08_80)] dark:bg-[oklch(0.72_0.08_80)]",
    text: "text-white dark:text-[oklch(0.18_0.03_80)]",
    swatch: "bg-[oklch(0.48_0.08_80)] dark:bg-[oklch(0.72_0.08_80)]",
    label: "evaluation",
  },
  "score-a": {
    fill: "bg-[oklch(0.45_0.1_250)] dark:bg-[oklch(0.7_0.1_250)]",
    text: "text-white",
    swatch: "bg-[oklch(0.45_0.1_250)] dark:bg-[oklch(0.7_0.1_250)]",
    label: "Similarity",
  },
  "score-b": {
    fill: "bg-[oklch(0.58_0.13_55)] dark:bg-[oklch(0.75_0.12_55)]",
    text: "text-[oklch(0.22_0.05_55)]",
    swatch: "bg-[oklch(0.58_0.13_55)] dark:bg-[oklch(0.75_0.12_55)]",
    label: "Recency",
  },
  "score-c": {
    fill: "bg-[oklch(0.52_0.11_185)] dark:bg-[oklch(0.72_0.1_185)]",
    text: "text-white dark:text-[oklch(0.15_0.02_185)]",
    swatch: "bg-[oklch(0.52_0.11_185)] dark:bg-[oklch(0.72_0.1_185)]",
    label: "Confidence",
  },
  "score-d": {
    fill: "bg-[oklch(0.5_0.12_25)] dark:bg-[oklch(0.68_0.11_25)]",
    text: "text-white",
    swatch: "bg-[oklch(0.5_0.12_25)] dark:bg-[oklch(0.68_0.11_25)]",
    label: "Trust",
  },
  "score-e": {
    fill: "bg-[oklch(0.48_0.09_145)] dark:bg-[oklch(0.7_0.09_145)]",
    text: "text-white dark:text-[oklch(0.15_0.03_145)]",
    swatch: "bg-[oklch(0.48_0.09_145)] dark:bg-[oklch(0.7_0.09_145)]",
    label: "Label",
  },
}

/** Map span name → viz tone for the flame graph. */
export function spanTone(name: string): VizTone {
  const n = name.toLowerCase()
  if (
    n.includes("auth") ||
    n.includes("rate_limit") ||
    n.includes("ratelimit")
  ) {
    return "auth"
  }
  if (
    n.includes("context") ||
    n.includes("retriev") ||
    n.includes("memory") ||
    n.includes("rank") ||
    n.includes("pack") ||
    n.includes("assembl")
  ) {
    return "context"
  }
  if (n.includes("provider") || n.includes("complete") || n.includes("llm")) {
    return "provider"
  }
  if (n.includes("tool")) return "tool"
  if (n.includes("stream")) return "stream"
  if (n.includes("eval") || n.includes("score")) return "eval"
  if (n.includes("proxy") || n.includes("chat") || n.includes("root"))
    return "root"
  return "root"
}

export const LATENCY_STAGES = [
  { key: "auth", label: "auth", tone: "auth" as VizTone },
  { key: "rate_limit", label: "rate limit", tone: "auth" as VizTone },
  { key: "context_retrieve", label: "retrieve", tone: "context" as VizTone },
  { key: "context_rank", label: "rank", tone: "context" as VizTone },
  { key: "context_pack", label: "pack", tone: "stream" as VizTone },
  { key: "provider", label: "provider", tone: "provider" as VizTone },
  { key: "stream", label: "stream", tone: "tool" as VizTone },
] as const

export const ASSEMBLY_TONES: VizTone[] = [
  "score-a",
  "context",
  "provider",
  "tool",
  "stream",
  "eval",
]
