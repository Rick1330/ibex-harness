export const NAV_LINKS = [
  {
    text: "Docs",
    href: "/docs/getting-started/introduction",
    match: "/docs",
  },
  {
    text: "Blog",
    href: "/blog",
    match: "/blog",
  },
  {
    text: "Releases",
    href: "/releases",
    match: "/releases",
  },
  {
    text: "Roadmap",
    href: "/roadmap",
    match: "/roadmap",
  },
] as const;

export function isLinkActive(pathname: string, match: string) {
  return match === "/docs"
    ? pathname.startsWith("/docs")
    : pathname.startsWith(match);
}
