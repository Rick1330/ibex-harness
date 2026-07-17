import { SectionShell } from "@/components/chrome/section-shell";
import { FEATURES } from "@/lib/landing-content";

export function LandingFeatures() {
  return (
    <SectionShell id="capabilities" section="§02" label="CAPABILITIES" hideHeader>
      <div className="grid gap-10 py-14 lg:grid-cols-2 lg:gap-16 lg:py-20">
        <div>
          <p className="mb-4 font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
            §02 · CAPABILITIES
          </p>
          <h2 className="max-w-[16ch] font-display text-[length:var(--text-4xl)] leading-[1.05] tracking-[-0.02em]">
            Built for agents that cannot afford{" "}
            <em className="italic">silent failure</em>.
          </h2>
          <p className="mt-5 max-w-[42ch] text-base leading-relaxed text-foreground-muted">
            One ingress. Every model request inspected, authorized, and traced
            before it leaves your perimeter.
          </p>
        </div>

        <ul className="divide-y divide-border border-y border-border">
          {FEATURES.map((feature) => (
            <li key={feature.index} className="py-5 first:pt-4 last:pb-4">
              <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-foreground-muted">
                [ {feature.index} ] {feature.tag}
              </p>
              <h3 className="mt-2 font-display text-2xl tracking-[-0.02em]">
                {feature.title}
              </h3>
              <p className="mt-2 max-w-[48ch] text-sm leading-relaxed text-foreground-muted">
                {feature.body}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </SectionShell>
  );
}
