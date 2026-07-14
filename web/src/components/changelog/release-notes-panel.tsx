"use client";

import { useMemo, useState } from "react";

import { ChangelogScopeFilter } from "@/components/changelog/changelog-scope-filter";
import { ReleaseSectionBlock } from "@/components/changelog/release-section-block";
import type { ReleaseEntry } from "@/lib/changelog";
import { collectScopes } from "@/lib/changelog";

type ReleaseNotesPanelProps = Readonly<{
  release: ReleaseEntry;
  showScopeFilter?: boolean;
}>;

export function ReleaseNotesPanel({
  release,
  showScopeFilter = true,
}: ReleaseNotesPanelProps) {
  const [activeScope, setActiveScope] = useState<string | null>(null);
  const scopes = useMemo(() => collectScopes(release), [release]);

  return (
    <div className="space-y-6">
      {showScopeFilter && scopes.length > 1 ? (
        <ChangelogScopeFilter
          scopes={scopes}
          activeScope={activeScope}
          onChange={setActiveScope}
        />
      ) : null}

      <div className="space-y-4">
        {release.sections.map((section) => (
          <ReleaseSectionBlock
            key={`${release.version}-${section.title}`}
            section={section}
            activeScope={activeScope}
          />
        ))}
      </div>
    </div>
  );
}
