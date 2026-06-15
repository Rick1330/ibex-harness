import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";
import { iconFromLucideName } from "@/lib/sidebar-icon-resolvers";
import { toNavIconName } from "@/lib/sidebar-icons";

type IconProps = Readonly<{
  name: string;
  className?: string;
}>;

function resolveLucideIcon(name: string): LucideIcon | undefined {
  return iconFromLucideName(toNavIconName(name));
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
