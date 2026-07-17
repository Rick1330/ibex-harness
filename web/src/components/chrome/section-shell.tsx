import type { ReactNode } from "react";

type SectionShellProps = Readonly<{
  section: string;
  label: string;
  meta?: string;
  children: ReactNode;
  className?: string;
  id?: string;
  /** Hide the top hairline label row when the section has its own eyebrow. */
  hideHeader?: boolean;
}>;

/** Editorial section chrome — hairlines + § label. No vertical writing-mode (breaks grid). */
export function SectionShell({
  section,
  label,
  meta,
  children,
  className = "",
  id,
  hideHeader = false,
}: SectionShellProps) {
  return (
    <section
      id={id}
      data-section={section}
      className={`landing-section relative border-b border-border ${className}`.trim()}
    >
      <div className="landing-inner">
        {!hideHeader ? (
          <header className="mb-8 flex flex-wrap items-baseline justify-between gap-3 border-b border-border pb-3 sm:mb-10">
            <p className="font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
              {section} · {label}
            </p>
            {meta ? (
              <p className="font-mono text-xs text-foreground-subtle">
                {meta}
              </p>
            ) : null}
          </header>
        ) : null}
        {children}
      </div>
    </section>
  );
}
