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
      data-copy
      data-copy-button
      data-copied={checked ? "true" : undefined}
      className={cn(
        "codeblock-copy-btn relative inline-flex items-center justify-center",
        className,
      )}
      onClick={onClick}
      {...props}
    >
      <Check
        aria-hidden
        className={cn("size-3.5 transition-transform", !checked && "scale-0")}
        strokeWidth={2}
      />
      <Copy
        aria-hidden
        className={cn(
          "absolute size-3.5 transition-transform",
          checked && "scale-0",
        )}
        strokeWidth={2}
      />
    </button>
  );
}
