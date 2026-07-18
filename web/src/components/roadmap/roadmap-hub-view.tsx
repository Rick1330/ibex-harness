import Link from "next/link";

import { BlogSectionRule } from "@/components/blog/blog-section-rule";
import { RoadmapPhaseNav } from "@/components/roadmap/roadmap-phase-nav";
import { RoadmapTimeline } from "@/components/roadmap/roadmap-timeline";
import { GITHUB_OWNER, GITHUB_REPO } from "@/lib/github";
import type { getPhaseTimeline, getRecentCompletedMilestones } from "@/lib/roadmap-hub";

type TimelinePhase = ReturnType<typeof getPhaseTimeline>[number];
type RecentMilestone = ReturnType<typeof getRecentCompletedMilestones>[number];

type RoadmapHubViewProps = Readonly<{
  phases: TimelinePhase[];
  recent: RecentMilestone[];
  completed: number;
  total: number;
  progressPct: number;
}>;

const REFERENCES = [
  { href: "/roadmap/current-state", label: "Current state" },
  { href: "/roadmap/findings", label: "Findings" },
  { href: "/roadmap/overview", label: "Phases overview" },
  { href: "/docs/adr", label: "ADRs" },
] as const;

/** Editorial roadmap hub — phase rail + vertical timeline (DESIGN_GUIDE §17). */
export function RoadmapHubView({
  phases,
  recent,
  completed,
  total,
  progressPct,
}: RoadmapHubViewProps) {
  const navPhases = phases.map((phase) => ({
    anchor: phase.anchor,
    phaseIndex: phase.phaseIndex,
    shortTitle: phase.shortTitle,
    status: phase.status,
  }));

  return (
    <div className="roadmap-hub">
      <header className="roadmap-intro">
        <h1 className="roadmap-title">Roadmap</h1>
        <p className="roadmap-lede">
          From foundation through memory, multi-provider, and production
          hardening — phases, milestones, and what ships next.
        </p>
        <div className="roadmap-progress-strip">
          <div className="roadmap-progress-meta">
            <span className="roadmap-progress-label">Overall</span>
            <span className="roadmap-progress-count">
              {completed} / {total} milestones · {progressPct}%
            </span>
          </div>
          <progress
            className="roadmap-progress-track"
            max={Math.max(total, 1)}
            value={completed}
            aria-label="Overall roadmap progress"
          />
        </div>
        <nav className="roadmap-refs" aria-label="Roadmap references">
          {REFERENCES.map((ref) => (
            <Link key={ref.href} href={ref.href} className="roadmap-ref-chip">
              {ref.label}
            </Link>
          ))}
        </nav>
      </header>

      <div className="roadmap-layout">
        <aside className="roadmap-aside">
          <div className="roadmap-aside-sticky">
            <RoadmapPhaseNav phases={navPhases} />
          </div>
        </aside>

        <div className="roadmap-feed">
          <BlogSectionRule>Timeline</BlogSectionRule>
          <RoadmapTimeline phases={phases} />

          <section className="roadmap-path" aria-labelledby="roadmap-path-heading">
            <BlogSectionRule id="roadmap-path-heading">Critical path</BlogSectionRule>
            <p className="roadmap-path-mono">
              Phase 0 → Phase 1 → Phase 1.5 → Phase 2 → Phase 3 → Phase 4 →
              Phase 5
            </p>
            <p className="roadmap-path-note">
              See the{" "}
              <Link href="/roadmap/overview">phases overview</Link> for
              dependencies and exit criteria.
            </p>
          </section>

          {recent.length > 0 ? (
            <section
              className="roadmap-recent"
              aria-labelledby="roadmap-recent-heading"
            >
              <BlogSectionRule id="roadmap-recent-heading">
                Recently completed
              </BlogSectionRule>
              <ul className="roadmap-recent-list">
                {recent.map((item) => (
                  <li key={item.url} className="roadmap-recent-row">
                    {item.milestoneId ? (
                      <span className="roadmap-recent-id">
                        {item.milestoneId}
                      </span>
                    ) : (
                      <span className="roadmap-recent-id" aria-hidden>
                        —
                      </span>
                    )}
                    <Link href={item.url} className="roadmap-recent-title">
                      {item.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <footer className="roadmap-footer">
            <p>
              Planning evolves with implementation. Follow{" "}
              <Link
                href={`https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                GitHub
              </Link>{" "}
              for merges and{" "}
              <Link href="/roadmap/current-state">current state</Link> for what
              ships today.
            </p>
          </footer>
        </div>
      </div>
    </div>
  );
}
