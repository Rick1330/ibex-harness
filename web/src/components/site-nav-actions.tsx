"use client";

import { Menu, X } from "lucide-react";

import { NavGithubLink } from "@/components/layout/nav-github-link";
import { NavSearch } from "@/components/layout/nav-search";
import { ThemeToggle } from "@/components/theme-toggle";

type SiteNavActionsProps = Readonly<{
  mobileOpen: boolean;
  onToggleMobile: () => void;
}>;

/** Right cluster: ⌘K · Theme · GitHub (DESIGN_GUIDE.md §8). */
export function SiteNavActions({
  mobileOpen,
  onToggleMobile,
}: SiteNavActionsProps) {
  return (
    <div className="site-nav-actions flex shrink-0 items-center gap-3">
      <NavSearch variant="icon" className="lg:hidden" />
      <NavSearch variant="compact" className="hidden lg:inline-flex" />
      <ThemeToggle />
      <NavGithubLink showLabel className="hidden sm:inline-flex" />
      <NavGithubLink className="inline-flex sm:hidden" />
      <button
        type="button"
        className="flex size-8 items-center justify-center rounded-sm border border-border text-foreground-muted transition-colors hover:bg-surface hover:text-foreground md:hidden"
        aria-expanded={mobileOpen}
        aria-controls="site-nav-mobile-drawer"
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
