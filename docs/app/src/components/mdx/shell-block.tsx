"use client";

import { Terminal } from "lucide-react";
import { useCallback, useRef } from "react";

import { CopyButton } from "@/components/mdx/copy-button";
import { cn } from "@/lib/cn";

type ShellBlockProps = Readonly<{
  command: string;
  className?: string;
}>;

export function ShellBlock({ command, className }: ShellBlockProps) {
  const areaRef = useRef<HTMLDivElement>(null);

  const onCopy = useCallback(async () => {
    await navigator.clipboard.writeText(command);
  }, [command]);

  return (
    <figure
      className={cn(
        "fd-codeblock nd-codeblock not-prose group relative my-7 overflow-hidden rounded-[4px]",
        className,
      )}
      data-language="bash"
      data-rehype-pretty-code-figure=""
    >
      <div className="codeblock-header">
        <figcaption className="codeblock-tab" data-rehype-pretty-code-title="">
          <Terminal
            aria-hidden
            className="codeblock-tab-icon size-3.5 shrink-0 opacity-60"
            strokeWidth={2}
          />
          <span className="truncate">Shell</span>
        </figcaption>
        <CopyButton className="codeblock-copy" onCopy={onCopy} />
      </div>
      <div ref={areaRef} className="codeblock-body">
        <pre className="overflow-x-auto font-mono text-[0.875rem] leading-[1.7]">
          <code>{command}</code>
        </pre>
      </div>
    </figure>
  );
}
