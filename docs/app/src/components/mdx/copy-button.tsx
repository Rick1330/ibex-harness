"use client";

import { Check, Copy } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";
import { useCopyButton } from "fumadocs-ui/components/api";

import { cn } from "@/lib/cn";

type CopyButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  onCopy: () => void;
};

export function CopyButton({ className, onCopy, ...props }: CopyButtonProps) {
  const [checked, onClick] = useCopyButton(onCopy);

  return (
    <button
      type="button"
      aria-label={checked ? "Copied" : "Copy code"}
      className={cn(
        "relative inline-flex size-7 items-center justify-center rounded-[4px]",
        "border border-border bg-panel-raised text-text-secondary",
        "hover:text-text-primary",
        className,
      )}
      onClick={onClick}
      {...props}
    >
      <Check
        className={cn(
          "size-3.5 transition-transform",
          !checked && "scale-0",
        )}
        strokeWidth={1.5}
      />
      <Copy
        className={cn(
          "absolute size-3.5 transition-transform",
          checked && "scale-0",
        )}
        strokeWidth={1.5}
      />
    </button>
  );
}
