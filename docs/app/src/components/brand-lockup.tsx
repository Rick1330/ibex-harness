import Link from "next/link";

import { WordmarkText } from "@/components/wordmark";
import { cn } from "@/lib/cn";

type BrandLockupProps = Readonly<{
  href?: string;
  ariaLabel?: string;
  showWordmark?: "md" | "always" | "never";
  className?: string;
}>;

export function BrandLockup({
  href = "/docs/getting-started/introduction",
  ariaLabel = "IBEX Harness docs home",
  showWordmark = "md",
  className,
}: BrandLockupProps) {
  const wordmarkClass =
    showWordmark === "always"
      ? "flex"
      : showWordmark === "never"
        ? "hidden"
        : "hidden md:flex";

  return (
    <Link
      href={href}
      aria-label={ariaLabel}
      className={cn(
        "group flex min-w-0 items-center gap-2.5 transition-opacity hover:opacity-90",
        className,
      )}
    >
      <span className="relative size-7 shrink-0">
        {/* eslint-disable-next-line @next/next/no-img-element -- static brand marks; avoids dev image optimizer latency */}
        <img
          src="/brand/ibex-mark-light.png"
          alt=""
          width={28}
          height={28}
          decoding="async"
          className="size-7 object-contain dark:hidden"
        />
        {/* eslint-disable-next-line @next/next/no-img-element -- static brand marks; avoids dev image optimizer latency */}
        <img
          src="/brand/ibex-mark-dark.png"
          alt=""
          width={28}
          height={28}
          decoding="async"
          className="hidden size-7 object-contain dark:block"
        />
      </span>
      <WordmarkText size="nav" className={wordmarkClass} />
    </Link>
  );
}
