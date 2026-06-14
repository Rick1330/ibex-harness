import * as LucideIcons from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";

type IconProps = {
  name: string;
  className?: string;
};

function resolveLucideIcon(name: string): LucideIcon | undefined {
  const icons = LucideIcons as Record<string, LucideIcon | unknown>;
  if (name in icons && typeof icons[name] === "function") {
    return icons[name] as LucideIcon;
  }

  const pascal = name
    .split(/[-_\s]+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");

  if (pascal in icons && typeof icons[pascal] === "function") {
    return icons[pascal] as LucideIcon;
  }

  return undefined;
}

export function Icon({ name, className }: IconProps) {
  const IconComponent = resolveLucideIcon(name);
  if (!IconComponent) return null;

  return (
    <IconComponent
      aria-hidden
      className={cn(
        "inline-block size-4 align-text-bottom text-text-secondary",
        className,
      )}
      strokeWidth={1.5}
    />
  );
}
