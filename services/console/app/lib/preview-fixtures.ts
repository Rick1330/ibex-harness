import type { SurfaceKey } from "~~/shared/operator/surfaces"

export type FixtureKind = "preview" | "demo"

export type FixtureModule = {
  file: string
  surface: SurfaceKey
  kind: FixtureKind
}

/**
 * Enumerated fixture registry for ADR-0089 §4.
 *
 * Preview fixtures are illustrative rows shown only on `preview` surfaces.
 * The demo module is the compile-time `import.meta.dev` substitution for
 * live-shaped reads; it is not a data mode and never activates in a
 * production build.
 */
export const FIXTURE_MODULES: FixtureModule[] = [
  { file: "access-preview.ts", surface: "access", kind: "preview" },
  { file: "analytics-preview.ts", surface: "analytics", kind: "preview" },
  { file: "audit-preview.ts", surface: "audit", kind: "preview" },
  { file: "budget-preview.ts", surface: "budgets", kind: "preview" },
  { file: "console-demo.ts", surface: "overview", kind: "demo" },
  { file: "directive-preview.ts", surface: "directives", kind: "preview" },
  { file: "drift-preview.ts", surface: "drift", kind: "preview" },
  { file: "incident-preview.ts", surface: "incidents", kind: "preview" },
  { file: "policy-preview.ts", surface: "policies", kind: "preview" },
  { file: "provider-preview.ts", surface: "providers", kind: "preview" },
  { file: "settings-preview.ts", surface: "settings", kind: "preview" },
  { file: "tool-preview.ts", surface: "mcp-tools", kind: "preview" },
]

export const PREVIEW_FIXTURE_FILES: string[] = FIXTURE_MODULES.filter((module) => module.kind === "preview").map(
  (module) => module.file,
)

export const DEMO_FIXTURE_FILES: string[] = FIXTURE_MODULES.filter((module) => module.kind === "demo").map(
  (module) => module.file,
)
