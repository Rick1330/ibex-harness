"use client";

import { Menu, X } from "lucide-react";

import { NavGithubLink } from "@/components/layout/nav-github-link";
import { NavSearch } from "@/components/layout/nav-search";
import { ThemeToggle } from "@/components/theme-toggle";

type SiteNavActionsProps = Readonly<{
  mobileOpen: boolean;
  onToggleMobile: () => void;
}>;

export function SiteNavActions({
  mobileOpen,
  onToggleMobile,
}: SiteNavActionsProps) {
  return (
    <div className="site-nav-actions flex shrink-0 items-center gap-1.5 sm:gap-2">
      <NavSearch variant="icon" className="lg:hidden" />
      <NavSearch variant="compact" className="hidden lg:inline-flex" />

      <NavGithubLink showLabel />

      <ThemeToggle />

      <button
        type="button"
        className="flex size-8 items-center justify-center rounded-md border border-border/80 text-muted-foreground transition-colors hover:bg-muted/35 hover:text-foreground md:hidden"
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
