import Link from "next/link";

import { PhaseCard } from "@/components/roadmap/phase-card";
import { RoadmapProgress } from "@/components/roadmap/roadmap-progress";
import { RoadmapReferenceCard } from "@/components/roadmap/reference-card";
import { GITHUB_OWNER, GITHUB_REPO } from "@/lib/github";
import type { getPhaseCards, getRecentCompletedMilestones } from "@/lib/roadmap-hub";

type PhaseCardData = ReturnType<typeof getPhaseCards>[number];
type RecentMilestone = ReturnType<typeof getRecentCompletedMilestones>[number];

export function RoadmapReferenceSection() {
  return (
    <section className="mb-12">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
        Reference
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <RoadmapReferenceCard
          href="/roadmap/current-state"
          title="Current state"
          description="What ships today, next tasks, and main branch SHA."
        />
        <RoadmapReferenceCard
          href="/roadmap/findings"
          title="Findings log"
          description="Plan pivots and surprises logged during delivery."
        />
        <RoadmapReferenceCard
          href="/roadmap/overview"
          title="Phases overview"
          description="Full phase table, dependencies, and sequencing."
        />
        <RoadmapReferenceCard
          href="/docs/adr"
          title="Architecture decisions"
          description="Accepted ADRs for auth, proxy, migrations, and docs."
        />
      </div>
    </section>
  );
}

export function RoadmapProgressSection({
  completed,
  total,
  progressPct,
}: Readonly<{
  completed: number;
  total: number;
  progressPct: number;
}>) {
  return (
    <section className="mb-12 rounded-xl border border-border bg-card p-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm font-semibold text-foreground">
          Overall milestone progress
        </span>
        <span className="text-sm font-bold tabular-nums text-foreground">
          {completed} / {total} completed ({progressPct}%)
        </span>
      </div>
      <RoadmapProgress value={progressPct} className="h-2" />
    </section>
  );
}

export function RoadmapCriticalPathSection() {
  return (
    <section className="mb-12">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
        Critical path
      </h2>
      <div className="rounded-xl border border-border bg-muted/10 p-5 font-mono text-sm leading-relaxed text-muted-foreground">
        Phase 0 → Phase 1 → Phase 1.5 (docs) → Phase 2 (provider) → Phase 3
        (memory/context) → Phase 4 (multi-provider) → Phase 5 (production
        hardening)
      </div>
      <p className="mt-3 text-sm text-muted-foreground">
        See the{" "}
        <Link href="/roadmap/overview" className="underline underline-offset-2 hover:text-foreground">
          phases overview
        </Link>{" "}
        for dependency detail and exit criteria.
      </p>
    </section>
  );
}

export function RoadmapRecentSection({
  recent,
}: Readonly<{ recent: RecentMilestone[] }>) {
  if (recent.length === 0) return null;

  return (
    <section className="mb-12">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
        Recently completed
      </h2>
      <ul className="divide-y divide-border rounded-xl border border-border bg-card">
        {recent.map((item) => (
          <li key={item.url}>
            <Link
              href={item.url}
              className="flex items-center justify-between gap-4 px-4 py-3 text-sm transition-colors hover:bg-muted/20"
            >
              <span className="font-medium text-foreground">{item.title}</span>
              {item.milestoneId ? (
                <span className="shrink-0 font-mono text-xs text-muted-foreground">
                  {item.milestoneId}
                </span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function RoadmapPhasesSection({
  phases,
}: Readonly<{ phases: PhaseCardData[] }>) {
  return (
    <section>
      <h2 className="mb-6 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
        Phases
      </h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {phases.map((phase) => (
          <PhaseCard key={phase.slug} {...phase} />
        ))}
      </div>
    </section>
  );
}

export function RoadmapHubFooter() {
  return (
    <footer className="mt-16 border-t border-border pt-8">
      <p className="text-center text-xs text-muted-foreground">
        Planning evolves with implementation. Follow{" "}
        <Link
          href={`https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}`}
          className="underline underline-offset-2 transition-colors hover:text-foreground"
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub
        </Link>{" "}
        for the latest merges and{" "}
        <Link
          href="/roadmap/current-state"
          className="underline underline-offset-2 transition-colors hover:text-foreground"
        >
          current state
        </Link>{" "}
        for what ships today.
      </p>
    </footer>
  );
}
