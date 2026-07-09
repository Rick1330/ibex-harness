"use client";

import {
  BookOpen,
  ChevronsUpDown,
  Gauge,
  Map,
  Newspaper,
  ScrollText,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "fumadocs-ui/components/ui/collapsible";

import { cn } from "@/lib/cn";
import type {
  MobileNavSectionConfig,
  MobileSectionIconId,
} from "@/lib/site-nav-config";

function resolveSectionIcon(iconId: MobileSectionIconId): LucideIcon {
  switch (iconId) {
    case "docs":
      return BookOpen;
    case "benchmarks":
      return Gauge;
    case "blog":
      return Newspaper;
    case "releases":
      return ScrollText;
    case "roadmap":
      return Map;
    default:
      return BookOpen;
  }
}

function SectionIcon({ iconId }: Readonly<{ iconId: MobileSectionIconId }>) {
  const Icon = resolveSectionIcon(iconId);
  return (
    <Icon
      className="size-4 shrink-0 text-text-primary"
      strokeWidth={1.5}
      aria-hidden
    />
  );
}

type MobileSectionSwitcherProps = Readonly<{
  sections: ReadonlyArray<MobileNavSectionConfig>;
  activeSectionId: string | null;
  onSelect: () => void;
}>;

type SectionRowProps = Readonly<{
  section: MobileNavSectionConfig;
  active?: boolean;
}>;

function SectionRow({ section, active = false }: SectionRowProps) {
  return (
    <>
      <SectionIcon iconId={section.iconId} />
      <div className="min-w-0 flex-1 text-start">
        <p className="text-sm font-medium text-text-primary">{section.title}</p>
        <p className="text-xs text-text-tertiary">{section.description}</p>
      </div>
      {active ? (
        <span className="sr-only">Current section</span>
      ) : null}
    </>
  );
}

export function MobileSectionSwitcher({
  sections,
  activeSectionId,
  onSelect,
}: MobileSectionSwitcherProps) {
  const [expanded, setExpanded] = useState(false);
  const activeSection = useMemo(() => {
    if (sections.length === 0) return null;
    return (
      sections.find((section) => section.id === activeSectionId) ?? sections[0]
    );
  }, [activeSectionId, sections]);

  if (!activeSection) return null;

  return (
    <Collapsible
      open={expanded}
      onOpenChange={setExpanded}
      className="mobile-section-switcher"
    >
      <CollapsibleTrigger
        className={cn(
          "flex w-full items-center gap-2 rounded-sm border border-border",
          "bg-panel-raised px-2 py-2 text-start",
          "hover:bg-panel transition-colors",
        )}
      >
        <SectionRow section={activeSection} active />
        <ChevronsUpDown
          className="me-1 size-4 shrink-0 text-text-secondary"
          strokeWidth={1.5}
          aria-hidden
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="mobile-section-switcher-panel mt-2 overflow-hidden rounded-sm border border-border bg-canvas">
        {sections.map((section) => {
          const isActive = section.id === activeSection.id;

          return (
            <Link
              key={section.id}
              href={section.href}
              prefetch
              onClick={() => {
                setExpanded(false);
                onSelect();
              }}
              className={cn(
                "flex w-full items-center gap-2 px-2 py-2 transition-colors",
                "hover:bg-panel-raised",
                isActive && "bg-panel-raised border-s-2 border-accent",
              )}
            >
              <SectionRow section={section} active={isActive} />
            </Link>
          );
        })}
      </CollapsibleContent>
    </Collapsible>
  );
}
