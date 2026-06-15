import { Github, Menu, X } from "lucide-react";
import Link from "next/link";

import { ThemeToggle } from "@/components/theme-toggle";
import { SiteNavLinks } from "@/components/site-nav-links";
import { GITHUB_OWNER, GITHUB_REPO } from "@/lib/github";

type SiteNavActionsProps = Readonly<{
  onDocs: boolean;
  mobileOpen: boolean;
  onToggleMobile: () => void;
}>;

export function SiteNavActions({
  onDocs,
  mobileOpen,
  onToggleMobile,
}: SiteNavActionsProps) {
  return (
    <div className="ml-auto flex shrink-0 items-center gap-1.5 ps-3 sm:gap-2">
      {onDocs ? (
        <Link
          href="/docs"
          className="hidden h-8 items-center rounded-md border border-border/80 bg-muted/25 px-2.5 text-xs font-medium text-muted-foreground transition-colors hover:border-border hover:bg-muted/45 hover:text-foreground lg:flex"
          title="Open search (⌘K)"
        >
          <kbd className="mr-1.5 rounded border border-border/80 bg-background px-1 py-0.5 font-mono text-[10px] text-muted-foreground">
            ⌘K
          </kbd>{" "}
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
        onClick={onToggleMobile}
      >
        {mobileOpen ? (
          <X className="size-4" strokeWidth={2} />
        ) : (
          <Menu className="size-4" strokeWidth={2} />
        )}
      </button>
    </div>
  );
}

type SiteNavMobileMenuProps = Readonly<{
  open: boolean;
  pathname: string;
  onNavigate: () => void;
}>;

export function SiteNavMobileMenu({ open, pathname, onNavigate }: SiteNavMobileMenuProps) {
  if (!open) return null;

  return (
    <nav
      id="site-nav-mobile"
      aria-label="Mobile site sections"
      className="border-t border-border/70 bg-background/95 px-4 py-3 md:hidden"
    >
      <div className="mx-auto flex max-w-[90rem] flex-col gap-1">
        <SiteNavLinks pathname={pathname} variant="mobile" onNavigate={onNavigate} />
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
  );
}
