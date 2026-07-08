import type { LucideIcon } from "lucide-react";
import { ExternalLink } from "lucide-react";
import Link from "next/link";

import { getNavIconForUrl, createNavIconQuery, resolveNavIcon, toNavIconName, toNavUrl, SidebarIcon } from "@/lib/sidebar-icons";
import { cn } from "@/lib/cn";

export type QuickLink = {
  title: string;
  href: string;
  icon?: LucideIcon;
  iconName?: string;
  external?: boolean;
  description?: string;
};

type QuickLinksProps = Readonly<{
  links: QuickLink[];
}>;

function linkIcon(link: QuickLink): LucideIcon {
  if (link.icon) return link.icon;
  if (link.iconName) {
    return (
      resolveNavIcon(createNavIconQuery(toNavIconName(link.iconName), toNavUrl(link.href))) ??
      getNavIconForUrl(toNavUrl(link.href))
    );
  }
  return getNavIconForUrl(toNavUrl(link.href));
}

export function QuickLinks({ links }: QuickLinksProps) {
  return (
    <div className="not-prose my-6 grid gap-3 sm:grid-cols-2">
      {links.map((link) => {
        const Icon = linkIcon(link);

        return (
          <Link
            className={cn(
              "group flex items-start gap-3 rounded-md border border-border bg-panel p-4",
              "transition-colors hover:bg-panel-raised",
            )}
            href={link.href}
            key={link.href}
            rel={link.external ? "noopener noreferrer" : undefined}
            target={link.external ? "_blank" : undefined}
          >
            <div className="flex size-9 shrink-0 items-center justify-center rounded-md border border-border bg-panel-raised">
              <SidebarIcon icon={Icon} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-text-primary">
                  {link.title}
                </span>
                {link.external ? (
                  <ExternalLink
                    className="size-3 text-text-tertiary"
                    strokeWidth={1.5}
                  />
                ) : null}
              </div>
              {link.description ? (
                <p className="mt-1 text-xs leading-relaxed text-text-secondary">
                  {link.description}
                </p>
              ) : null}
            </div>
          </Link>
        );
      })}
    </div>
  );
}
