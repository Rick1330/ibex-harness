import { BENCHMARKS } from "@/lib/landing-content";

/**
 * Stats strip — full-bleed 4 equal columns with hairline dividers
 * (screenshot reference / DESIGN_GUIDE.md §12.6).
 */
export function LandingBenchmarks() {
  return (
    <section
      id="benchmarks"
      aria-label="Key stats"
      className="landing-stats-section border-y border-border"
    >
      <div className="landing-stats-grid">
        {BENCHMARKS.map((metric) => (
          <div key={metric.label} className="landing-stat-cell">
            <p className="landing-stat-label">{metric.label}</p>
            <p className="landing-stat-value">{metric.value}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
