import type { Metadata } from "next";
import fs from "node:fs";
import path from "node:path";

type ReleaseType = "major" | "minor" | "patch";
type ReleaseSection = Readonly<{ title: string; items: string[] }>;
type ReleaseEntry = Readonly<{
  version: string;
  date: string | null;
  type: ReleaseType;
  summary: string | null;
  sections: ReleaseSection[];
}>;

const RELEASE_HEADER =
  /^## \[?(\d+\.\d+\.\d+)\]?(?:\s+\(([^)]+)\)|(?:\s+[-—]\s+(.+)))?$/;
const SECTION_HEADER = /^###\s+(.+)$/;

const versionBadge = {
  major:
    "rounded-full bg-text-primary px-2.5 py-0.5 font-mono text-xs font-bold text-canvas",
  minor:
    "rounded-full border border-border bg-panel px-2.5 py-0.5 font-mono text-xs font-bold text-text-primary",
  patch:
    "rounded-full border border-border bg-panel-raised px-2.5 py-0.5 font-mono text-xs font-bold text-text-secondary",
} as const;

function parseReleaseType(version: string): ReleaseType {
  const [major, minor] = version.split(".").map((part) => Number(part) || 0);
  if (major > 0) return "major";
  if (minor > 0) return "minor";
  return "patch";
}

function normalizeDate(raw: string | null): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!trimmed || trimmed === "YYYY-MM-DD") return null;
  return trimmed;
}

function shouldIgnoreItem(item: string): boolean {
  const normalized = item.toLowerCase();
  return normalized === "_tbd_" || normalized === "(example)" || normalized.startsWith("(example) ");
}

type MutableSection = { title: string; items: string[] };
type MutableRelease = {
  version: string;
  date: string | null;
  type: ReleaseType;
  summary: string | null;
  sections: MutableSection[];
};

function flushCurrentRelease(list: ReleaseEntry[], current: MutableRelease | null): void {
  if (current) list.push(current);
}

function createRelease(match: RegExpExecArray): MutableRelease {
  return {
    version: match[1],
    date: normalizeDate(match[2] ?? match[3] ?? null),
    type: parseReleaseType(match[1]),
    summary: null,
    sections: [],
  };
}

function parseSection(line: string): MutableSection | null {
  const sectionMatch = SECTION_HEADER.exec(line);
  if (!sectionMatch) return null;
  return { title: sectionMatch[1], items: [] };
}

function appendBullet(line: string, section: MutableSection | null): boolean {
  const bulletMatch = /^[-*]\s+/.exec(line);
  if (!bulletMatch || !section) return false;
  const item = line.slice(bulletMatch[0].length).trim();
  if (item && !shouldIgnoreItem(item)) {
    section.items.push(item);
  }
  return true;
}

function shouldIgnoreTextLine(line: string, hasSummary: boolean): boolean {
  if (!line) return true;
  if (line.startsWith("---")) return true;
  return hasSummary;
}

function readReleasesFromChangelog(): ReleaseEntry[] {
  const changelogPath = path.resolve(process.cwd(), "../CHANGELOG.md");
  const lines = fs.readFileSync(changelogPath, "utf8").split(/\r?\n/);

  const releases: ReleaseEntry[] = [];
  let current: MutableRelease | null = null;
  let section: MutableSection | null = null;

  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith("## [Unreleased]")) {
      flushCurrentRelease(releases, current);
      current = null;
      section = null;
      continue;
    }

    const releaseMatch = RELEASE_HEADER.exec(line);
    if (releaseMatch) {
      flushCurrentRelease(releases, current);
      current = createRelease(releaseMatch);
      section = null;
      continue;
    }

    if (!current) continue;
    const parsedSection = parseSection(line);
    if (parsedSection) {
      section = parsedSection;
      current.sections.push(section);
      continue;
    }

    if (appendBullet(line, section)) continue;
    if (shouldIgnoreTextLine(line, Boolean(current.summary))) continue;
    if (!section) current.summary = line;
  }

  flushCurrentRelease(releases, current);
  return releases;
}

export const metadata: Metadata = {
  title: "Changelog",
  description: "Version history and release notes generated from CHANGELOG.md.",
};

export default function ReleasesPage() {
  const allReleases = readReleasesFromChangelog();

  return (
    <div className="mx-auto max-w-2xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
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
        {allReleases.length === 0 ? (
          <div className="rounded-lg border border-border bg-panel p-6 text-sm text-text-secondary">
            No tagged releases yet. Release entries appear here automatically
            when the version release pipeline updates `CHANGELOG.md` for the first
            published version.
          </div>
        ) : null}

        {allReleases.length > 1 ? (
          <div className="absolute bottom-0 left-[11px] top-2 w-px bg-border" />
        ) : null}

        <div className="space-y-0">
          {allReleases.map((release) => {
            const releaseType = release.type;
            const badgeClass = versionBadge[releaseType] ?? versionBadge.minor;

            return (
              <div
                key={release.version}
                className="relative flex gap-6 pb-10 last:pb-0"
              >
                <div className="relative z-10 mt-1 shrink-0">
                  <div className="flex size-6 items-center justify-center rounded-full border-2 border-border bg-canvas">
                    <div className="size-2 rounded-full bg-text-primary" />
                  </div>
                </div>

                <div className="min-w-0 flex-1">
                  <div className="mb-2 flex flex-wrap items-center gap-3">
                    <span className="font-mono text-xl font-bold tracking-tight text-text-primary">
                      v{release.version}
                    </span>
                    <span className={badgeClass}>{releaseType}</span>
                    {release.date ? (
                      <time className="text-sm text-text-secondary">
                        {new Date(release.date).toLocaleDateString("en-US", {
                          year: "numeric",
                          month: "long",
                          day: "numeric",
                        })}
                      </time>
                    ) : null}
                  </div>

                  {release.summary ? (
                    <p className="mb-3 text-base text-text-secondary">
                      {release.summary}
                    </p>
                  ) : null}

                  <div className="space-y-4 text-sm leading-relaxed text-text-secondary">
                    {release.sections
                      .filter((section) => section.items.length > 0)
                      .map((section) => (
                      <section key={`${release.version}-${section.title}`}>
                        <h2 className="mb-2 text-base font-semibold text-text-primary">
                          {section.title}
                        </h2>
                        <ul className="list-disc space-y-1 pl-5">
                          {section.items.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                    ))}
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
