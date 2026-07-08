import Link from "next/link";

import { cn } from "@/lib/cn";
import { isLinkActive, LANDING_NAV_LINK, NAV_LINKS } from "@/lib/site-nav-config";

type SiteNavLinksProps = Readonly<{
  pathname: string;
  variant: "desktop" | "mobile";
  onNavigate?: () => void;
}>;

function desktopLinkClass(isActive: boolean): string {
  const base =
    "relative flex h-full items-center whitespace-nowrap px-2 text-xs font-medium transition-colors lg:px-4 lg:text-sm";
  if (isActive) {
    return cn(
      base,
      "text-foreground after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:bg-foreground",
    );
  }
  return cn(base, "text-muted-foreground hover:text-foreground");
}

function mobileLinkClass(isActive: boolean): string {
  const base = "rounded-md px-3 py-2.5 text-sm font-medium transition-colors";
  if (isActive) {
    return cn(base, "bg-muted/50 text-foreground");
  }
  return cn(base, "text-muted-foreground hover:bg-muted/30 hover:text-foreground");
}

export function SiteNavLinks({ pathname, variant, onNavigate }: SiteNavLinksProps) {
  const isDesktop = variant === "desktop";
  const homeActive = pathname === "/" || pathname === "";

  const homeClass = isDesktop
    ? desktopLinkClass(homeActive)
    : mobileLinkClass(homeActive);

  return (
    <>
      <Link
        href={LANDING_NAV_LINK.href}
        prefetch
        onClick={onNavigate}
        className={homeClass}
      >
        {LANDING_NAV_LINK.text}
      </Link>
      {NAV_LINKS.map((link) => {
        const isActive = isLinkActive(pathname, link.match);
        const className = isDesktop
          ? desktopLinkClass(isActive)
          : mobileLinkClass(isActive);

        return (
          <Link
            key={link.href}
            href={link.href}
            prefetch
            onClick={onNavigate}
            className={className}
          >
            {link.text}
          </Link>
        );
      })}
    </>
  );
}
