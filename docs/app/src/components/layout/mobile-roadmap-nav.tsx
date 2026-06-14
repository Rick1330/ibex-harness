"use client";

import { SearchToggle } from "fumadocs-ui/components/layout/search-toggle";
import { NavbarSidebarTrigger } from "fumadocs-ui/layouts/docs.client";

export function MobileRoadmapNav() {
  return (
    <header className="flex h-12 items-center gap-2 border-b border-border px-4 md:hidden">
      <NavbarSidebarTrigger className="-ms-1" />
      <span className="text-sm font-medium text-foreground">Roadmap</span>
      <div className="flex-1" />
      <SearchToggle hideIfDisabled />
    </header>
  );
}
