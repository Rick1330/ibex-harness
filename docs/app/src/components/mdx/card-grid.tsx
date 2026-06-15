import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { resolveNavIcon, createNavIconQuery, toNavIconName, toNavUrl, SidebarIcon } from "@/lib/sidebar-icons";
import { cn } from "@/lib/cn";

type CardGridProps = Readonly<{
  children: ReactNode;
}>;

export function CardGrid({ children }: CardGridProps) {
  return (
    <div className="not-prose my-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {children}
    </div>
  );
}

type DocCardCategory = "guide" | "reference" | "tutorial" | "example";

type DocCardProps = Readonly<{
  title: string;
  description: string;
  href: string;
  icon?: LucideIcon;
  iconName?: string;
  badge?: string;
  category?: DocCardCategory;
}>;

function categoryLabel(category: DocCardCategory): string {
  switch (category) {
    case "guide":
      return "Guide";
    case "reference":
      return "Reference";
    case "tutorial":
      return "Tutorial";
    case "example":
      return "Example";
  }
}

export function DocCard({
  title,
  description,
  href,
  icon,
  iconName,
  badge,
  category,
}: DocCardProps) {
  const isExternal = href.startsWith("http");
  const CardIcon =
    icon ??
    (iconName ? resolveNavIcon(createNavIconQuery(toNavIconName(iconName), toNavUrl(href))) : undefined);

  return (
    <Link
      className={cn(
        "group relative flex flex-col gap-3 rounded-md border border-border bg-panel p-5",
        "transition-[background-color,border-color,box-shadow] duration-150 ease-out",
        "hover:border-border-strong hover:shadow-[0_4px_12px_rgb(0_0_0/0.08)]",
        "dark:hover:shadow-[0_4px_12px_rgb(0_0_0/0.4)]",
      )}
      href={href}
      rel={isExternal ? "noopener noreferrer" : undefined}
      target={isExternal ? "_blank" : undefined}
    >
      {badge ? (
        <span className="absolute end-4 top-4 rounded-[4px] border border-border bg-panel-raised px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-text-secondary">
          {badge}
        </span>
      ) : null}

      {CardIcon ? (
        <div className="flex size-10 items-center justify-center rounded-md border border-border bg-panel-raised">
          <SidebarIcon className="text-text-primary" icon={CardIcon} />
        </div>
      ) : null}

      <h3 className="font-medium text-text-primary group-hover:text-text-primary">
        {title}
      </h3>

      {category ? (
        <span className="text-[11px] font-medium uppercase tracking-wide text-text-tertiary">
          {categoryLabel(category)}
        </span>
      ) : null}

      <p className="line-clamp-2 text-sm leading-relaxed text-text-secondary">
        {description}
      </p>

      <span className="mt-auto pt-1 text-sm font-medium text-text-secondary group-hover:text-text-primary">
        Learn more →
      </span>
    </Link>
  );
}
