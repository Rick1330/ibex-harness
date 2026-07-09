import { METRICS } from "@/lib/landing-content";

export function LandingMetrics() {
  return (
    <section id="metrics" className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
      <div className="grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
        {METRICS.map((metric) => (
          <div key={metric.label} className="bg-paper p-8 text-center">
            <div className="text-4xl font-extrabold tracking-tight">
              {metric.value}
            </div>
            <div className="mt-2 text-xs tracking-widest text-muted-foreground">
              {metric.label.toUpperCase()}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
