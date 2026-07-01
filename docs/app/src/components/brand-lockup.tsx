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

export function BrandLockup({
  href = LANDING_SITE_URL,
  ariaLabel = "IBEX Harness home",
  showWordmark = "md",
  className,
}: BrandLockupProps) {
  const wordmarkClass =
    showWordmark === "always"
      ? "flex"
      : showWordmark === "never"
        ? "hidden"
        : "hidden md:flex";

  const linkClass = cn(
    "group flex min-w-0 items-center gap-2.5 transition-opacity hover:opacity-90",
    className,
  );

  const content = (
    <>
      <span className="relative size-7 shrink-0">
        {/* eslint-disable-next-line @next/next/no-img-element -- static brand marks; avoids dev image optimizer latency */}
        <img
          src="/brand/ibex-mark-light.png"
          alt=""
          width={28}
          height={28}
          decoding="async"
          fetchPriority="high"
          className="size-7 object-contain dark:hidden"
        />
        {/* eslint-disable-next-line @next/next/no-img-element -- static brand marks; avoids dev image optimizer latency */}
        <img
          src="/brand/ibex-mark-dark.png"
          alt=""
          width={28}
          height={28}
          decoding="async"
          fetchPriority="high"
          className="hidden size-7 object-contain dark:block"
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
