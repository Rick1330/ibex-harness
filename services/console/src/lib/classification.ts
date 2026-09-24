export type DataMode = "production" | "preview" | "test"
export type SurfaceStatus =
  "implemented" | "preview-only" | "specified-not-implemented" | "deferred"
export type SurfaceClassification = {
  status: SurfaceStatus
  dataMode: "none" | "fixture"
  note: string
}

export const SURFACE_CLASSIFICATIONS: Record<string, SurfaceClassification> = {
  overview: {
    status: "preview-only",
    dataMode: "fixture",
    note: "Dashboard presentation uses deterministic fixtures only when preview is explicitly enabled.",
  },
  auth: {
    status: "specified-not-implemented",
    dataMode: "none",
    note: "Authentication is owned by AuthService; this is presentation only.",
  },
  onboarding: {
    status: "specified-not-implemented",
    dataMode: "none",
    note: "Organization setup has no client-side authority or success handler.",
  },
  shell: {
    status: "implemented",
    dataMode: "none",
    note: "Shared dashboard presentation is transplanted from the supplied mock.",
  },
  deferred: {
    status: "deferred",
    dataMode: "none",
    note: "This surface remains visually available but has no live data contract.",
  },
}

export function classifyPath(pathname: string): SurfaceClassification {
  if (pathname === "/dashboard" || pathname === "/dashboard/")
    return SURFACE_CLASSIFICATIONS.overview
  if (pathname === "/login") return SURFACE_CLASSIFICATIONS.auth
  if (pathname.startsWith("/onboarding"))
    return SURFACE_CLASSIFICATIONS.onboarding
  if (pathname.startsWith("/dashboard")) {
    if (
      /^\/dashboard\/(explore|analytics|sessions|directives|incidents|settings|billing|agents|memories|drift)/.test(
        pathname,
      )
    )
      return SURFACE_CLASSIFICATIONS.deferred
    return SURFACE_CLASSIFICATIONS.shell
  }
  return SURFACE_CLASSIFICATIONS.shell
}

export function resolveDataMode(
  env: Record<string, string | undefined> = process.env,
): DataMode {
  if (env.NODE_ENV === "production") return "production"
  if (
    env.CONSOLE_DATA_MODE === "preview" &&
    env.CONSOLE_PREVIEW === "1"
  )
    return "preview"
  if (env.CONSOLE_DATA_MODE === "test") return "test"
  return "production"
}

export function isPreviewEnabled(
  env: Record<string, string | undefined> = process.env,
) {
  const mode = resolveDataMode(env)
  return mode === "preview" || mode === "test"
}

export function isDashboardPreviewEnabled(
  env: Record<string, string | undefined> = process.env,
) {
  const mode = resolveDataMode(env)
  return (
    env.NODE_ENV !== "production" &&
    env.NEXT_PUBLIC_CONSOLE_PREVIEW === "1" &&
    env.CONSOLE_DATA_MODE === "preview" &&
    env.CONSOLE_PREVIEW === "1" &&
    mode === "preview"
  )
}

export const PREVIEW_MODE = process.env.NEXT_PUBLIC_CONSOLE_PREVIEW === "1"
