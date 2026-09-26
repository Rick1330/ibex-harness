import routeInventory from "./route-classification.json"

export type DataMode = "production" | "preview" | "test"
export type SurfaceStatus =
  | "implemented"
  | "preview-only"
  | "specified-not-implemented"
  | "deferred"
  | "unavailable"
export type SurfaceClassification = {
  status: SurfaceStatus
  dataMode: "none" | "fixture"
  note: string
}

type InventoryStatus = "implemented" | "preview-only" | "deferred" | "unavailable"
type InventoryEntry = { status: InventoryStatus; data_mode: "none" | "fixture"; owner: string }
const routes = routeInventory.routes as Record<string, InventoryEntry>

function pathMatches(pattern: string, pathname: string): boolean {
  const expected = pattern.split("/").filter(Boolean)
  const actual = pathname.split("/").filter(Boolean)
  return expected.length === actual.length && expected.every((part, index) =>
    part.startsWith(":") ? actual[index].length > 0 : part === actual[index],
  )
}

export function classifyPath(pathname: string): SurfaceClassification {
  const normalized = pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname
  const inventoryPath =
    Object.keys(routes).find((pattern) => pathMatches(pattern, normalized)) ?? null
  const entry = inventoryPath ? routes[inventoryPath] : null
  if (entry) {
    return {
      status: entry.status,
      dataMode: entry.data_mode,
      note: `${entry.owner} owns this ${entry.status} surface.`,
    }
  }
  // Unknown nested dashboard paths stay fail-closed rather than inheriting a
  // fixture-bearing page or being classified as an implemented shell route.
  if (normalized.startsWith("/dashboard/")) {
    return {
      status: "deferred",
      dataMode: "none",
      note: "This dashboard route is not in the D1 allowlist.",
    }
  }
  return {
    status: "unavailable",
    dataMode: "none",
    note: "No canonical Console route is registered for this path.",
  }
}

export function resolveDataMode(
  env: Record<string, string | undefined> = process.env,
): DataMode {
  if (env.NODE_ENV === "production") return "production"
  if (env.CONSOLE_DATA_MODE === "preview" && env.CONSOLE_PREVIEW === "1")
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

/** Live D1 mode is opt-in, read-only, and requires a server-only API origin. */
export function isLiveD1Enabled(
  env: Record<string, string | undefined> = process.env,
) {
  return (
    env.CONSOLE_DATA_MODE === "live" &&
    env.CONSOLE_READ_ONLY === "1" &&
    Boolean(env.IBEX_OPERATOR_API_ORIGIN)
  )
}

export type DashboardBoundary = "preview" | "unavailable"

export function resolveDashboardBoundary(
  env: Record<string, string | undefined> = process.env,
): DashboardBoundary {
  return isDashboardPreviewEnabled(env) ? "preview" : "unavailable"
}

export const PREVIEW_MODE = process.env.NEXT_PUBLIC_CONSOLE_PREVIEW === "1"
