"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";

const TABS = [
  { href: "/benchmarks", label: "Overview", match: "/benchmarks", exact: true as const },
  { href: "/benchmarks/load", label: "Load", match: "/benchmarks/load", exact: false as const },
  { href: "/benchmarks/history", label: "History", match: "/benchmarks/history", exact: false as const },
] as const;

export function BenchmarkTabNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Benchmark sections"
      className="mb-8 flex flex-wrap gap-1 border-b border-border"
    >
      {TABS.map((tab) => {
        const isActive = tab.exact
          ? pathname === tab.href
          : pathname.startsWith(tab.match);

        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "relative -mb-px rounded-t-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "border-b-2 border-foreground text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
