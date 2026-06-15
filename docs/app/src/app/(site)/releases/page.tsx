import type { Metadata } from "next";

import { releasesSource } from "@/lib/source";
import { getMDXComponents } from "@/mdx-components";

const versionBadge = {
  major:
    "rounded-full bg-text-primary px-2.5 py-0.5 font-mono text-xs font-bold text-canvas",
  minor:
    "rounded-full border border-border bg-panel px-2.5 py-0.5 font-mono text-xs font-bold text-text-primary",
  patch:
    "rounded-full border border-border bg-panel-raised px-2.5 py-0.5 font-mono text-xs font-bold text-text-secondary",
} as const;

export const metadata: Metadata = {
  title: "Changelog",
  description: "Full version history and release notes for IBEX Harness.",
};

export default function ReleasesPage() {
  const mdxComponents = getMDXComponents();
  const allReleases = releasesSource
    .getPages()
    .sort(
      (a, b) =>
        new Date(String(b.data.date)).getTime() -
        new Date(String(a.data.date)).getTime(),
    );

  return (
    <div className="mx-auto max-w-2xl px-4 py-16 md:px-6">
      <header className="mb-10 border-b border-border pb-8">
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-text-tertiary">
          Releases
        </p>
        <h1 className="mb-3 text-4xl font-bold tracking-tight text-text-primary">
          Changelog
        </h1>
        <p className="text-lg text-text-secondary">
          Full version history and release notes for IBEX Harness.
        </p>
      </header>

      <div className="relative">
        {allReleases.length > 1 ? (
          <div className="absolute bottom-0 left-[11px] top-2 w-px bg-border" />
        ) : null}

        <div className="space-y-0">
          {allReleases.map((release) => {
            const MdxContent = release.data.body;
            const releaseType = release.data.type ?? "patch";
            const badgeClass =
              versionBadge[releaseType as keyof typeof versionBadge] ??
              versionBadge.minor;

            return (
              <div key={release.url} className="relative flex gap-6 pb-10 last:pb-0">
                <div className="relative z-10 mt-1 shrink-0">
                  <div className="flex size-6 items-center justify-center rounded-full border-2 border-border bg-canvas">
                    <div className="size-2 rounded-full bg-text-primary" />
                  </div>
                </div>

                <div className="min-w-0 flex-1">
                  <div className="mb-2 flex flex-wrap items-center gap-3">
                    <span className="font-mono text-xl font-bold tracking-tight text-text-primary">
                      v{release.data.version}
                    </span>
                    <span className={badgeClass}>{releaseType}</span>
                    <time className="text-sm text-text-secondary">
                      {new Date(String(release.data.date)).toLocaleDateString(
                        "en-US",
                        {
                          year: "numeric",
                          month: "long",
                          day: "numeric",
                        },
                      )}
                    </time>
                  </div>

                  <h2 className="mb-3 text-base font-semibold text-text-primary">
                    {release.data.title}
                  </h2>

                  <div className="prose docs-prose max-w-none text-sm leading-relaxed text-text-secondary">
                    <MdxContent components={mdxComponents} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
