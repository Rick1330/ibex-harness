import type { DataMode } from "@/lib/classification"

export type PreviewFixture = {
  readonly mode: "preview" | "test"
  readonly label: "PREVIEW DATA" | "TEST DATA"
  readonly cards: readonly {
    readonly label: string
    readonly value: string
    readonly delta: string
    readonly tone: "up" | "down"
  }[]
  readonly chart: readonly { readonly label: string; readonly value: number }[]
  readonly rows: readonly {
    readonly name: string
    readonly type: string
    readonly status: "Done" | "In progress" | "Not started"
    readonly target: string
    readonly owner: string
  }[]
}

const fixture: PreviewFixture = {
  mode: "preview",
  label: "PREVIEW DATA",
  cards: [
    { label: "Total requests", value: "12,580", delta: "+12.5%", tone: "up" },
    { label: "Active agents", value: "1,234", delta: "-2.0%", tone: "down" },
    { label: "Success rate", value: "98.7%", delta: "+4.5%", tone: "up" },
    { label: "Context latency", value: "184ms", delta: "-8.2%", tone: "up" },
  ],
  chart: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(
    (label, index) => ({ label, value: [38, 52, 44, 72, 61, 84, 69][index] }),
  ),
  rows: [
    {
      name: "Context assembly",
      type: "Overview",
      status: "Done",
      target: "99.9%",
      owner: "Platform",
    },
    {
      name: "Provider routing",
      type: "Directive",
      status: "In progress",
      target: "p95 < 240ms",
      owner: "Runtime",
    },
    {
      name: "Memory retrieval",
      type: "Capability",
      status: "Done",
      target: "98.0%",
      owner: "Memory",
    },
    {
      name: "Evidence export",
      type: "Governance",
      status: "Not started",
      target: "D2 gate",
      owner: "Security",
    },
  ],
}

export function getPreviewFixture(mode: DataMode): PreviewFixture {
  if (mode !== "preview" && mode !== "test")
    throw new Error("PREVIEW_FIXTURES_DISABLED_IN_PRODUCTION")
  return mode === "test" ? { ...fixture, mode, label: "TEST DATA" } : fixture
}
