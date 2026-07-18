import Link from "next/link";

import { WordmarkText } from "@/components/wordmark";
import { cn } from "@/lib/cn";
import { LANDING_SITE_URL } from "@/lib/site-nav-config";

type BrandLockupProps = Readonly<{
  href?: string;
  ariaLabel?: string;
  showWordmark?: "md" | "always" | "never";
  className?: string;
}>;

function isExternalHref(href: string): boolean {
  return href.startsWith("http://") || href.startsWith("https://");
}

function wordmarkVisibilityClass(
  showWordmark: "md" | "always" | "never",
): string | undefined {
  if (showWordmark === "always") return undefined;
  if (showWordmark === "never") return "brand-wordmark-never";
  return "brand-wordmark-md";
}

/**
 * Brand mark + formal “IBEX Harness” wordmark.
 * Light → ibex-mark-light.png (dark ink). Dark → ibex-mark-dark.png (light ink).
 * Visibility uses CSS under `html.dark` — do NOT use Tailwind `hidden dark:block`
 * (fumadocs unlayered `.hidden` wins and keeps the dark mark forever).
 */
export function BrandLockup({
  href = LANDING_SITE_URL,
  ariaLabel = "IBEX Harness home",
  showWordmark = "md",
  className,
}: BrandLockupProps) {
  const wordmarkClass = wordmarkVisibilityClass(showWordmark);

  const linkClass = cn(
    "group flex min-w-0 items-center gap-2.5 transition-opacity hover:opacity-90",
    className,
  );

  const content = (
    <>
      <span className="brand-mark relative size-7 shrink-0 overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element -- static brand marks */}
        <img
          src="/brand/ibex-mark-light.png"
          alt=""
          width={28}
          height={28}
          decoding="async"
          fetchPriority="high"
          className="brand-mark-light size-7 object-contain"
        />
        {/* eslint-disable-next-line @next/next/no-img-element -- static brand marks */}
        <img
          src="/brand/ibex-mark-dark.png"
          alt=""
          width={28}
          height={28}
          decoding="async"
          fetchPriority="high"
          className="brand-mark-dark size-7 object-contain"
        />
      </span>
      <WordmarkText size="nav" className={wordmarkClass} />
    </>
  );

  if (isExternalHref(href)) {
    return (
      <a href={href} aria-label={ariaLabel} className={linkClass}>
        {content}
      </a>
    );
  }

  return (
    <Link href={href} aria-label={ariaLabel} className={linkClass}>
      {content}
    </Link>
  );
}
