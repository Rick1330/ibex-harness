"use client";

import { FileCode, Terminal, type LucideIcon } from "lucide-react";
import {
  forwardRef,
  useCallback,
  useRef,
  type HTMLAttributes,
  type ReactNode,
} from "react";

import { CopyButton } from "@/components/mdx/copy-button";
import {
  getLanguageDisplayLabel,
  isShellLanguage,
  languageFromChildren,
  parseCodeLanguage,
  resolveCodeLanguage,
} from "@/lib/code-language";
import { cn } from "@/lib/cn";

export type PreProps = HTMLAttributes<HTMLPreElement> & {
  title?: string;
  icon?: ReactNode;
  "data-language"?: string;
};

type CodeblockHeaderProps = Readonly<{
  tabLabel: string;
  LabelIcon: LucideIcon;
  onCopy: () => Promise<void>;
}>;

function CodeblockHeader({ tabLabel, LabelIcon, onCopy }: CodeblockHeaderProps) {
  return (
    <div className="codeblock-header">
      <figcaption className="codeblock-tab" data-rehype-pretty-code-title="">
        <LabelIcon
          aria-hidden
          className="codeblock-tab-icon size-3.5 shrink-0 opacity-60"
          strokeWidth={2}
        />
        <span className="truncate">{tabLabel}</span>
      </figcaption>
      <CopyButton className="codeblock-copy" onCopy={onCopy} />
    </div>
  );
}

type CodeblockBodyProps = Readonly<{
  areaRef: React.RefObject<HTMLDivElement | null>;
  showHeader: boolean;
  onCopy: () => Promise<void>;
  preRef: React.Ref<HTMLPreElement>;
  className?: string;
  dataLanguage?: string;
  lang?: string;
  children: ReactNode;
  preProps: HTMLAttributes<HTMLPreElement>;
}>;

function CodeblockBody({
  areaRef,
  showHeader,
  onCopy,
  preRef,
  className,
  dataLanguage,
  lang,
  children,
  preProps,
}: CodeblockBodyProps) {
  return (
    <div ref={areaRef} className="codeblock-body">
      {showHeader ? null : <CopyButton className="codeblock-copy" onCopy={onCopy} />}
      <pre
        ref={preRef}
        className={cn(
          "overflow-x-auto font-mono text-[0.875rem] leading-[1.75] focus-visible:outline-none",
          className,
        )}
        data-language={dataLanguage ?? lang}
        {...preProps}
      >
        {children}
      </pre>
    </div>
  );
}

export const Pre = forwardRef<HTMLPreElement, PreProps>(function Pre(
  {
    title,
    className,
    children,
    icon: _icon,
    "data-language": dataLanguage,
    ...props
  },
  ref,
) {
  const areaRef = useRef<HTMLDivElement>(null);
  const lang =
    dataLanguage ?? parseCodeLanguage(className) ?? languageFromChildren(children);
  const tabLabel = getLanguageDisplayLabel(lang, title);
  const meta = resolveCodeLanguage(lang, title);
  const languageId = meta?.id ?? lang ?? "code";
  const shell = isShellLanguage(languageId);
  const showHeader = Boolean(tabLabel);

  const onCopy = useCallback(async () => {
    const pre = areaRef.current?.querySelector("pre");
    if (!pre) return;
    const clone = pre.cloneNode(true) as HTMLElement;
    clone.querySelectorAll(".nd-copy-ignore").forEach((node) => {
      node.remove();
    });
    await navigator.clipboard.writeText(clone.textContent ?? "");
  }, []);

  const LabelIcon = shell ? Terminal : meta?.icon ?? FileCode;

  return (
    <figure
      className="fd-codeblock nd-codeblock not-prose group relative my-7 overflow-hidden rounded-[4px]"
      data-codeblock
      data-language={languageId}
      data-rehype-pretty-code-figure=""
      {...(title ? { title } : {})}
    >
      {showHeader && tabLabel ? (
        <CodeblockHeader tabLabel={tabLabel} LabelIcon={LabelIcon} onCopy={onCopy} />
      ) : null}
      <CodeblockBody
        areaRef={areaRef}
        showHeader={showHeader}
        onCopy={onCopy}
        preRef={ref}
        className={className}
        dataLanguage={dataLanguage}
        lang={lang}
        preProps={props}
      >
        {children}
      </CodeblockBody>
    </figure>
  );
});
