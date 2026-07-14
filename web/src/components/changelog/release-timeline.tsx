"use client";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "fumadocs-ui/components/ui/collapsible";
import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { ReleaseNotesPanel } from "@/components/changelog/release-notes-panel";
import { releaseTypeBadgeClass } from "@/components/changelog/release-type-badge";
import { cn } from "@/lib/cn";
import type { ReleaseEntry } from "@/lib/changelog";

type ReleaseTimelineProps = Readonly<{
  releases: ReleaseEntry[];
}>;

function formatDate(date: string | null): string | null {
  if (!date) return null;
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

function OlderReleaseEntry({ release }: Readonly<{ release: ReleaseEntry }>) {
  const [open, setOpen] = useState(false);
  const badgeClass = releaseTypeBadgeClass(release.type);
  const formattedDate = formatDate(release.date);
  const itemCount = release.sections.reduce(
    (sum, section) => sum + section.items.length,
    0,
  );

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="relative flex gap-3 sm:gap-6">
        <div className="relative z-10 mt-1 shrink-0">
          <div className="flex size-6 items-center justify-center rounded-sm border-2 border-border bg-canvas">
            <div className="size-2 rounded-sm bg-text-tertiary" />
          </div>
        </div>

        <div className="min-w-0 flex-1 pb-8">
          <CollapsibleTrigger
            className={cn(
              "flex w-full flex-wrap items-center gap-2 text-start sm:gap-3",
              "hover:text-text-primary",
            )}
          >
            <span className="font-mono text-lg font-bold tracking-tight text-text-primary sm:text-xl">
              v{release.version}
            </span>
            <span className={badgeClass}>{release.type}</span>
            {formattedDate ? (
              <time className="w-full text-sm text-text-secondary sm:w-auto">
                {formattedDate}
              </time>
            ) : null}
            <span className="font-mono text-xs text-text-tertiary">
              {itemCount} changes
            </span>
            <ChevronDown
              className={cn(
                "ms-auto size-4 shrink-0 text-text-tertiary transition-transform duration-150",
                open && "rotate-180",
              )}
              aria-hidden
            />
          </CollapsibleTrigger>

          <CollapsibleContent className="mt-4">
            <ReleaseNotesPanel release={release} showScopeFilter={false} />
          </CollapsibleContent>
        </div>
      </div>
    </Collapsible>
  );
}

export function ReleaseTimeline({ releases }: ReleaseTimelineProps) {
  if (releases.length === 0) return null;

  return (
    <section>
      <h2 className="mb-6 text-sm font-semibold uppercase tracking-widest text-text-tertiary">
        Previous releases
      </h2>
      <div className="relative">
        <div className="absolute bottom-0 left-[11px] top-2 w-px bg-border" />
        <div className="space-y-0">
          {releases.map((release) => (
            <OlderReleaseEntry key={release.version} release={release} />
          ))}
        </div>
      </div>
    </section>
  );
}
