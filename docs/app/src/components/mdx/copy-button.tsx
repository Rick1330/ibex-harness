"use client";

import { Check, Copy } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type MouseEventHandler,
} from "react";

import { cn } from "@/lib/cn";

type CopyButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  onCopy: () => void | Promise<void>;
};

export function CopyButton({
  className,
  onCopy,
  onClick: onClickProp,
  ...props
}: CopyButtonProps) {
  const [checked, setChecked] = useState(false);
  const timeoutRef = useRef<number | null>(null);

  const onClick: MouseEventHandler<HTMLButtonElement> = useCallback(
    async (event) => {
      onClickProp?.(event);
      if (event.defaultPrevented) return;

      try {
        await onCopy();
      } catch {
        return;
      }

      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
      setChecked(true);
      timeoutRef.current = window.setTimeout(() => setChecked(false), 1500);
    },
    [onCopy, onClickProp],
  );

  useEffect(() => {
    return () => {
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    };
  }, []);

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
          "size-4 transition-transform",
          !checked && "scale-0",
        )}
        strokeWidth={1.5}
      />
      <Copy
        className={cn(
          "absolute size-4 transition-transform",
          checked && "scale-0",
        )}
        strokeWidth={1.5}
      />
    </button>
  );
}
