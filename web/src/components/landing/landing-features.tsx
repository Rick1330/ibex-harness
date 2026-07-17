import { SectionShell } from "@/components/chrome/section-shell";
import { Reveal } from "@/components/landing/reveal";
import { FEATURES } from "@/lib/landing-content";

export function LandingFeatures() {
  return (
    <SectionShell
      id="capabilities"
      section="§02"
      label="CAPABILITIES"
      docHref="/docs/architecture/overview"
    >
      <div className="grid gap-px border border-border bg-border sm:grid-cols-2">
        {FEATURES.map((feature, index) => (
          <Reveal key={feature.index} delay={index * 60}>
            <article className="group h-full bg-background p-7 transition-colors hover:bg-surface-1">
              <p className="font-mono text-xs text-foreground-muted">
                {feature.index}
              </p>
              <h3 className="mt-4 font-display text-[1.75rem] leading-tight tracking-[-0.02em]">
                {feature.title}
              </h3>
              <p className="mt-3 max-w-[52ch] text-sm leading-relaxed text-foreground-muted">
                {feature.body}
              </p>
              <pre className="mt-6 overflow-x-auto rounded-sm bg-surface-2 px-3 py-2 font-mono text-xs text-foreground">
                {feature.snippet}
              </pre>
            </article>
          </Reveal>
        ))}
      </div>
    </SectionShell>
  );
}
