import Link from "next/link";
import type { ReactNode } from "react";

type SectionShellProps = Readonly<{
  id?: string;
  section: string;
  label: string;
  meta?: string;
  docHref?: string;
  docLabel?: string;
  children: ReactNode;
  className?: string;
}>;

/**
 * Spec-sheet chrome (§7): hairlines, mono eyebrow, sticky § rail on ≥lg.
 * Rail sits outside content at -4rem so it never collapses the grid.
 */
export function SectionShell({
  id,
  section,
  label,
  meta,
  docHref,
  docLabel = "Read section",
  children,
  className = "",
}: SectionShellProps) {
  return (
    <section
      id={id}
      className={`landing-section relative border-b border-border ${className}`.trim()}
    >
      <div className="landing-inner relative py-[clamp(4rem,3rem+4vw,7rem)]">
        {/* Left § rail — absolute so it cannot shrink content */}
        <p
          className="pointer-events-none absolute -left-16 top-8 hidden font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted lg:block"
          style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
          aria-hidden
        >
          {section}
        </p>

        <header className="mb-10 flex flex-wrap items-baseline justify-between gap-3">
          <p className="font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
            {section} · {label}
          </p>
          {meta ? (
            <p className="font-mono text-xs text-foreground-subtle">{meta}</p>
          ) : null}
        </header>

        {children}

        {docHref ? (
          <footer className="mt-10 flex justify-end">
            <Link
              href={docHref}
              className="font-mono text-xs text-foreground-muted transition-colors hover:text-accent"
            >
              {docLabel} ↗
            </Link>
          </footer>
        ) : null}
      </div>
    </section>
  );
}
