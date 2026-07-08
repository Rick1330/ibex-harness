import { Reveal } from "@/components/landing/reveal";
import { FEATURES } from "@/lib/landing-content";

export function LandingFeatures() {
  return (
    <section id="features" className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
      <div className="mb-12 max-w-2xl">
        <p className="mb-3 text-xs tracking-widest text-muted-foreground">
          {"// CAPABILITIES"}
        </p>
        <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
          Built for agents that cannot afford silent failure.
        </h2>
      </div>
      <div className="grid gap-px border border-border bg-border sm:grid-cols-2">
        {FEATURES.map((feature, index) => (
          <Reveal key={feature.tag} delay={index * 80}>
            <article className="group h-full bg-paper p-7 transition-colors hover:bg-card">
              <div className="flex items-start justify-between">
                <span className="text-xs text-muted-foreground">{feature.tag}</span>
                <pre
                  className="text-[10px] leading-tight text-muted-foreground transition-colors group-hover:text-accent"
                  aria-hidden
                >
                  {feature.art.join("\n")}
                </pre>
              </div>
              <h3 className="mt-6 text-lg font-bold">{feature.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                {feature.body}
              </p>
            </article>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
