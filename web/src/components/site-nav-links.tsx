import Link from "next/link";

import { cn } from "@/lib/cn";
import { isLinkActive, NAV_LINKS } from "@/lib/site-nav-config";

type SiteNavLinksProps = Readonly<{
  pathname: string;
  variant: "desktop" | "mobile";
  onNavigate?: () => void;
}>;

/** Desktop: 14px muted, active = ink + 2px accent underline offset 6px (§8). */
function desktopLinkClass(isActive: boolean): string {
  const base =
    "relative py-1 text-sm transition-colors duration-[var(--dur-1)]";
  if (isActive) {
    return cn(base, "text-foreground");
  }
  return cn(base, "text-foreground-muted hover:text-foreground");
}

function mobileLinkClass(isActive: boolean): string {
  const base = "rounded-md px-3 py-2.5 text-sm font-medium transition-colors";
  if (isActive) {
    return cn(base, "bg-surface text-foreground");
  }
  return cn(base, "text-foreground-muted hover:bg-surface hover:text-foreground");
}

export function SiteNavLinks({ pathname, variant, onNavigate }: SiteNavLinksProps) {
  const isDesktop = variant === "desktop";

  return (
    <>
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
            aria-current={isActive ? "page" : undefined}
            className={cn(className, isDesktop && "inline-flex items-center")}
          >
            {link.text}
            {isDesktop && isActive ? (
              <span
                className="absolute -bottom-[6px] left-0 right-0 h-0.5 bg-accent"
                aria-hidden
              />
            ) : null}
          </Link>
        );
      })}
    </>
  );
}
