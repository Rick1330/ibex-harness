import type { ReactNode } from "react";

type SectionShellProps = Readonly<{
  id?: string;
  section: string;
  label: string;
  children: ReactNode;
  className?: string;
  /** Hide the § eyebrow (e.g. stats strip). */
  hideEyebrow?: boolean;
}>;

/** Section chrome — meta eyebrow + 1200px inner (DESIGN_GUIDE.md §12). */
export function SectionShell({
  id,
  section,
  label,
  children,
  className = "",
  hideEyebrow = false,
}: SectionShellProps) {
  return (
    <section
      id={id}
      className={`landing-section relative border-b border-border ${className}`.trim()}
    >
      <div className="landing-inner landing-section-pad">
        {hideEyebrow ? null : (
          <p className="landing-eyebrow mb-8">
            {section} · {label}
          </p>
        )}
        {children}
      </div>
    </section>
  );
}
