import { FLOW } from "@/lib/landing-content";

export function LandingFlow() {
  return (
    <section id="flow" className="border-y border-border">
      <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
        <div className="mb-12 max-w-2xl">
          <p className="mb-3 text-xs tracking-widest text-muted-foreground">
            {"// REQUEST PATH"}
          </p>
          <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            Every LLM call passes through one gate.
          </h2>
        </div>
        <div className="grid gap-6 md:grid-cols-4">
          {FLOW.map((step) => (
            <div key={step.step} className="relative">
              <div className="mb-4 text-5xl font-extrabold text-border">
                {step.step}
              </div>
              <p className="font-bold">
                <span className="text-muted-foreground">{step.step}. </span>
                {step.name}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {step.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
