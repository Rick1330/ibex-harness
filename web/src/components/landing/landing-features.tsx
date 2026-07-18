import { SectionShell } from "@/components/chrome/section-shell";
import { cn } from "@/lib/cn";
import { FEATURES } from "@/lib/landing-content";

/** §02 · Capabilities (DESIGN_GUIDE.md §12.3). */
export function LandingFeatures() {
  return (
    <SectionShell id="capabilities" section="§02" label="CAPABILITIES">
      <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-16">
        <div className="lg:col-span-5 md:sticky md:top-[calc(var(--topbar-h)+1.5rem)] md:self-start">
          <h2 className="landing-h2 max-w-[16ch]">
            Built for agents that cannot afford silent failure.
          </h2>
          <p className="landing-body mt-5 max-w-[40ch]">
            One ingress. Every model request inspected, authorized, and traced
            before it leaves your perimeter.
          </p>
        </div>

        <div className="lg:col-span-7">
          <ul className="border-t border-border">
            {FEATURES.map((feature) => (
              <li
                key={feature.index}
                className={cn(
                  "grid gap-3 border-b border-border py-6 transition-colors duration-[var(--dur-2)] sm:grid-cols-[160px_1fr] sm:gap-6",
                  feature.index === "03" ? "bg-surface" : "hover:bg-surface",
                )}
              >
                <p className="px-4 font-mono text-[11px] tracking-[0.08em] text-foreground-muted sm:px-0">
                  [{feature.index}] {feature.slug}
                </p>
                <div className="px-4 sm:px-0">
                  <h3 className="landing-h3">{feature.title}</h3>
                  <p className="landing-small mt-2 max-w-[48ch]">
                    {feature.body}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </SectionShell>
  );
}
