import Link from "next/link";

import { cn } from "@/lib/cn";
import { isLinkActive, NAV_LINKS } from "@/lib/site-nav-config";

type SiteNavLinksProps = {
  pathname: string;
  variant: "desktop" | "mobile";
  onNavigate?: () => void;
};

export function SiteNavLinks({ pathname, variant, onNavigate }: SiteNavLinksProps) {
  const isDesktop = variant === "desktop";

  return (
    <>
      {NAV_LINKS.map((link) => {
        const isActive = isLinkActive(pathname, link.match);

        return (
          <Link
            key={link.href}
            href={link.href}
            onClick={onNavigate}
            className={cn(
              isDesktop
                ? cn(
                    "relative flex h-full items-center whitespace-nowrap px-3 text-sm font-medium transition-colors lg:px-4",
                    isActive
                      ? "text-foreground after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:bg-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )
                : cn(
                    "rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-muted/50 text-foreground"
                      : "text-muted-foreground hover:bg-muted/30 hover:text-foreground",
                  ),
            )}
          >
            {link.text}
          </Link>
        );
      })}
    </>
  );
}
