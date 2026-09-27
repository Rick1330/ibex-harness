/** Shared Explore return-path sanitizer for live inspector pages. */

export type ExploreSearchParam = string | string[] | undefined

export function safeExploreReturnHref(raw: ExploreSearchParam): string {
  const value = Array.isArray(raw) ? raw[0] : raw
  if (!value?.startsWith("/dashboard/explore")) return "/dashboard/explore"
  if (value.includes("//") || value.includes("\\")) return "/dashboard/explore"
  return value
}
