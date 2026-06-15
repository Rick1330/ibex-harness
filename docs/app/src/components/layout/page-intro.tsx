import { cn } from "@/lib/cn";

type PageIntroProps = Readonly<{
  title?: string;
  description?: string;
  section?: string;
  hideTitle?: boolean;
}>;

export function PageIntro({
  title,
  description,
  section,
  hideTitle = false,
}: PageIntroProps) {
  const showTitle = !hideTitle && title;

  return (
    <div
      className={cn(
        "docs-page-intro mb-10 border-b border-border pb-8",
        !showTitle && !description && "mb-6 pb-0 border-none",
      )}
    >
      {section ? (
        <div className="mb-3">
          <span className="text-xs font-semibold uppercase tracking-widest text-text-tertiary">
            {section}
          </span>
        </div>
      ) : null}

      {showTitle ? (
        <h1
          className={cn(
            "text-[2.25rem] font-bold leading-tight tracking-tight",
            "text-text-primary",
          )}
        >
          {title}
        </h1>
      ) : null}

      {description ? (
        <p
          className={cn(
            "max-w-[44rem] text-[1.0625rem] leading-relaxed text-text-secondary",
            showTitle && "mt-4",
          )}
        >
          {description}
        </p>
      ) : null}
    </div>
  );
}
