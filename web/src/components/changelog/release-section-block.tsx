"use client";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "fumadocs-ui/components/ui/collapsible";
import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";

import { ChangeItemRow } from "@/components/changelog/change-item-row";
import {
  sectionAccentClass,
  sectionIcon,
} from "@/components/changelog/section-icons";
import { cn } from "@/lib/cn";
import type { ChangeItem, ReleaseSection } from "@/lib/changelog";

type ReleaseSectionBlockProps = Readonly<{
  section: ReleaseSection;
  activeScope: string | null;
  defaultExpanded?: boolean;
}>;

function filterByScope(items: ChangeItem[], scope: string | null): ChangeItem[] {
  if (!scope) return items;
  return items.filter((item) => item.scope === scope);
}

export function ReleaseSectionBlock({
  section,
  activeScope,
  defaultExpanded = false,
}: ReleaseSectionBlockProps) {
  const Icon = sectionIcon(section.title);
  const accent = sectionAccentClass(section.title);

  const filteredHighlights = useMemo(
    () => filterByScope(section.highlights, activeScope),
    [section.highlights, activeScope],
  );
  const filteredItems = useMemo(
    () => filterByScope(section.items, activeScope),
    [section.items, activeScope],
  );

  const remainder = useMemo(() => {
    const highlightSet = new Set(
      section.highlights.map(
        (item) =>
          `${item.scope ?? ""}:${item.description}:${item.issueNumber ?? ""}`,
      ),
    );
    return filteredItems.filter(
      (item) =>
        !highlightSet.has(
          `${item.scope ?? ""}:${item.description}:${item.issueNumber ?? ""}`,
        ),
    );
  }, [filteredItems, section.highlights]);

  const [expanded, setExpanded] = useState(defaultExpanded);
  const hasRemainder = remainder.length > 0;
  const totalCount = filteredItems.length;

  if (totalCount === 0) return null;

  return (
    <section className="rounded-md border border-border bg-card p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-center gap-2 sm:gap-3">
        <div
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-panel",
            accent,
          )}
        >
          <Icon className="size-4" strokeWidth={1.75} aria-hidden />
        </div>
        <h3 className="min-w-0 text-sm font-semibold text-text-primary sm:text-base">
          {section.title}
        </h3>
        <span className="rounded-[4px] border border-border bg-panel px-2 py-0.5 font-mono text-xs text-text-tertiary">
          {totalCount}
        </span>
      </div>

      {filteredHighlights.length > 0 ? (
        <ul className="space-y-3">
          {filteredHighlights.map((item) => (
            <ChangeItemRow
              key={`${section.title}-hl-${item.scope ?? "none"}-${item.description}-${item.issueNumber ?? item.commitSha ?? ""}`}
              item={item}
            />
          ))}
        </ul>
      ) : null}

      {hasRemainder ? (
        <Collapsible
          open={expanded}
          onOpenChange={setExpanded}
          className={filteredHighlights.length > 0 ? "mt-4" : undefined}
        >
          <CollapsibleTrigger
            className={cn(
              "flex w-full items-center gap-2 text-sm font-medium text-text-secondary",
              "hover:text-text-primary",
            )}
          >
            <ChevronDown
              className={cn(
                "size-4 shrink-0 transition-transform duration-150",
                expanded && "rotate-180",
              )}
              aria-hidden
            />
            {expanded
              ? "Hide additional changes"
              : `Show all ${totalCount} changes`}
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-3 border-t border-border pt-3">
            <ul className="space-y-3">
              {remainder.map((item) => (
                <ChangeItemRow
                  key={`${section.title}-full-${item.scope ?? "none"}-${item.description}-${item.issueNumber ?? item.commitSha ?? ""}`}
                  item={item}
                  showCommit
                />
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      ) : null}
    </section>
  );
}
