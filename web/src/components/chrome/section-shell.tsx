import Link from "next/link";
import type { ReactNode } from "react";

type SectionShellProps = Readonly<{
  section: string;
  label: string;
  meta?: string;
  docHref?: string;
  docLabel?: string;
  children: ReactNode;
  className?: string;
  id?: string;
}>;

/** Editorial section chrome — § numeral rail, hairlines, optional doc ref. */
export function SectionShell({
  section,
  label,
  meta,
  docHref,
  docLabel = "Read section",
  children,
  className = "",
  id,
}: SectionShellProps) {
  return (
    <section
      id={id}
      className={`relative border-y border-border ${className}`.trim()}
    >
      <div className="mx-auto max-w-[var(--container)] px-5 sm:px-8">
        <div className="relative grid gap-8 py-16 lg:grid-cols-[3.5rem_1fr] lg:py-20">
          <div className="hidden lg:block">
            <p
              className="sticky top-[calc(var(--site-nav-height)+1.5rem)] font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted [writing-mode:vertical-rl] [text-orientation:mixed]"
              aria-hidden
            >
              {section}
            </p>
          </div>

          <div className="min-w-0">
            <header className="mb-10 flex flex-wrap items-baseline justify-between gap-3 border-b border-border pb-4">
              <p className="font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
                {section} · {label}
              </p>
              {meta ? (
                <p className="font-mono text-xs tabular-nums text-foreground-subtle">
                  {meta}
                </p>
              ) : null}
            </header>

            {children}

            {docHref ? (
              <footer className="mt-10 flex justify-end border-t border-border pt-4">
                <Link
                  href={docHref}
                  className="font-mono text-xs text-foreground-muted transition-colors hover:text-accent"
                >
                  {docLabel} ↗
                </Link>
              </footer>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
