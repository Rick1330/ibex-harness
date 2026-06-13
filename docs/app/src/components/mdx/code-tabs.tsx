"use client";

import * as Tabs from "@radix-ui/react-tabs";
import {
  Children,
  isValidElement,
  useMemo,
  type ReactElement,
  type ReactNode,
} from "react";

import { cn } from "@/lib/cn";

type CodeTabProps = {
  label: string;
  value?: string;
  children: ReactNode;
};

type CodeTabsProps = {
  defaultValue?: string;
  children: ReactNode;
};

export function CodeTab({ children }: CodeTabProps) {
  return <>{children}</>;
}

function collectTabs(children: ReactNode) {
  return Children.toArray(children)
    .filter(isValidElement)
    .map((child, index) => {
      const props = (child as ReactElement<CodeTabProps>).props;
      const value =
        props.value ?? props.label.toLowerCase().replace(/\s+/g, "-");
      return {
        value,
        label: props.label,
        content: props.children,
        key: value || String(index),
      };
    });
}

export function CodeTabs({ defaultValue, children }: CodeTabsProps) {
  const tabs = useMemo(() => collectTabs(children), [children]);
  const initial = defaultValue ?? tabs[0]?.value ?? "";

  if (tabs.length === 0) return null;

  return (
    <Tabs.Root className="my-6" defaultValue={initial}>
      <Tabs.List className="flex gap-0 border-b border-border">
        {tabs.map((tab) => (
          <Tabs.Trigger
            className={cn(
              "rounded-t-[4px] border border-transparent px-4 py-2 text-sm text-text-secondary",
              "hover:text-text-primary",
              "data-[state=active]:border-border data-[state=active]:border-b-transparent",
              "data-[state=active]:bg-panel-raised data-[state=active]:text-text-primary",
            )}
            key={tab.key}
            value={tab.value}
          >
            {tab.label}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {tabs.map((tab) => (
        <Tabs.Content
          className="rounded-b-[4px] border border-t-0 border-border bg-panel [&_.fd-codeblock]:my-0 [&_.fd-codeblock]:rounded-t-none [&_.fd-codeblock]:border-t-0"
          key={tab.key}
          value={tab.value}
        >
          {tab.content}
        </Tabs.Content>
      ))}
    </Tabs.Root>
  );
}
