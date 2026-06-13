"use client";

import {
  forwardRef,
  useCallback,
  useRef,
  type HTMLAttributes,
  type ReactNode,
} from "react";

import { CopyButton } from "@/components/mdx/copy-button";
import { cn } from "@/lib/cn";

export type PreProps = HTMLAttributes<HTMLPreElement> & {
  title?: string;
  icon?: ReactNode;
};

export const Pre = forwardRef<HTMLPreElement, PreProps>(function Pre(
  { title, className, children, icon: _icon, ...props },
  ref,
) {
  const areaRef = useRef<HTMLDivElement>(null);

  const onCopy = useCallback(async () => {
    const pre = areaRef.current?.querySelector("pre");
    if (!pre) return;
    const clone = pre.cloneNode(true) as HTMLElement;
    clone.querySelectorAll(".nd-copy-ignore").forEach((node) => {
      node.remove();
    });
    await navigator.clipboard.writeText(clone.textContent ?? "");
  }, []);

  return (
    <figure className="fd-codeblock group relative my-6 overflow-hidden rounded-[4px] border border-border bg-panel text-[13.5px] leading-[1.65]">
      {title ? (
        <div className="flex h-7 items-center border-b border-border bg-panel-raised px-3">
          <figcaption className="truncate font-mono text-xs text-text-tertiary">
            {title}
          </figcaption>
        </div>
      ) : null}
      <div ref={areaRef} className="relative">
        <CopyButton
          className="absolute right-2 top-2 z-[2] opacity-0 transition-opacity group-hover:opacity-100"
          onCopy={onCopy}
        />
        <pre
          ref={ref}
          className={cn(
            "overflow-x-auto p-4 font-mono leading-[1.65] focus-visible:outline-none",
            className,
          )}
          {...props}
        >
          {children}
        </pre>
      </div>
    </figure>
  );
});
