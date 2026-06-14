"use client";

import { Github, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/cn";
import { GITHUB_OWNER, GITHUB_REPO } from "@/lib/github";

const NAV_LINKS = [
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

function isLinkActive(pathname: string, match: string) {
  return match === "/docs"
    ? pathname.startsWith("/docs")
    : pathname.startsWith(match);
}

export function SiteNav() {
  const pathname = usePathname();
  const onDocs = pathname.startsWith("/docs");
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header
      data-site-nav
      className="site-nav sticky top-0 z-50 w-full border-b border-border/80 bg-background/90 backdrop-blur-xl supports-[backdrop-filter]:bg-background/80"
    >
      <div className="site-nav-inner mx-auto flex h-[var(--site-nav-height)] w-full max-w-[90rem] items-stretch gap-0 px-4 sm:px-6 lg:px-8">
        <Link
          href="/docs/getting-started/introduction"
          className="group flex shrink-0 items-center gap-2.5 border-e border-border/70 pe-4 sm:pe-6"
        >
          <div className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-foreground shadow-sm">
            <span className="text-[10px] font-black leading-none text-background">
              I
            </span>
          </div>
          <div className="hidden items-baseline gap-1 sm:flex">
            <span className="text-sm font-semibold tracking-tight text-foreground">
              IBEX
            </span>
            <span className="text-sm font-normal tracking-tight text-muted-foreground">
              Harness
            </span>
          </div>
        </Link>

        <nav
          aria-label="Site sections"
          className="hidden min-w-0 flex-1 items-stretch ps-1 md:flex"
        >
          {NAV_LINKS.map((link) => {
            const isActive = isLinkActive(pathname, link.match);

            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "relative flex h-full items-center whitespace-nowrap px-3 text-sm font-medium transition-colors lg:px-4",
                  isActive
                    ? "text-foreground after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:bg-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {link.text}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-1.5 ps-3 sm:gap-2">
          {onDocs ? (
            <Link
              href="/docs"
              className="hidden h-8 items-center rounded-md border border-border/80 bg-muted/25 px-2.5 text-xs font-medium text-muted-foreground transition-colors hover:border-border hover:bg-muted/45 hover:text-foreground lg:flex"
              title="Open search (⌘K)"
            >
              <kbd className="mr-1.5 rounded border border-border/80 bg-background px-1 py-0.5 font-mono text-[10px] text-muted-foreground">
                ⌘K
              </kbd>
              Search
            </Link>
          ) : null}

          <Link
            href={`https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}`}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden h-8 items-center gap-2 rounded-md border border-border/80 bg-background px-2.5 text-sm font-medium text-muted-foreground transition-colors hover:border-border hover:bg-muted/35 hover:text-foreground sm:flex sm:px-3"
          >
            <Github className="size-4" strokeWidth={2} />
            <span className="hidden sm:inline">GitHub</span>
          </Link>

          <ThemeToggle />

          <button
            type="button"
            className="flex size-8 items-center justify-center rounded-md border border-border/80 text-muted-foreground transition-colors hover:bg-muted/35 hover:text-foreground md:hidden"
            aria-expanded={mobileOpen}
            aria-controls="site-nav-mobile"
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            onClick={() => setMobileOpen((open) => !open)}
          >
            {mobileOpen ? (
              <X className="size-4" strokeWidth={2} />
            ) : (
              <Menu className="size-4" strokeWidth={2} />
            )}
          </button>
        </div>
      </div>

      {mobileOpen ? (
        <nav
          id="site-nav-mobile"
          aria-label="Mobile site sections"
          className="border-t border-border/70 bg-background/95 px-4 py-3 md:hidden"
        >
          <div className="mx-auto flex max-w-[90rem] flex-col gap-1">
            {NAV_LINKS.map((link) => {
              const isActive = isLinkActive(pathname, link.match);

              return (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setMobileOpen(false)}
                  className={cn(
                    "rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-muted/50 text-foreground"
                      : "text-muted-foreground hover:bg-muted/30 hover:text-foreground",
                  )}
                >
                  {link.text}
                </Link>
              );
            })}
            <Link
              href={`https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 flex items-center gap-2 rounded-md px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted/30 hover:text-foreground sm:hidden"
            >
              <Github className="size-4" strokeWidth={2} />
              GitHub
            </Link>
          </div>
        </nav>
      ) : null}
    </header>
  );
}
