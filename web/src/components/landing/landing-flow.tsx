import { SectionShell } from "@/components/chrome/section-shell";
import { FLOW } from "@/lib/landing-content";

export function LandingFlow() {
  return (
    <SectionShell
      id="request-path"
      section="§03"
      label="REQUEST PATH"
      meta="trace_id 7f3a…c21 · duration 17.4ms · status 200"
      docHref="/docs/architecture/overview"
    >
      <div className="overflow-hidden rounded-md border border-border bg-surface-1">
        <div className="grid gap-6 p-6 md:grid-cols-4">
          {FLOW.map((step, index) => (
            <div key={step.step} className="relative min-w-0">
              {index < FLOW.length - 1 ? (
                <span
                  className="pointer-events-none absolute left-[calc(100%+0.25rem)] top-5 hidden h-px w-[calc(100%-1rem)] bg-border md:block"
                  aria-hidden
                />
              ) : null}
              <div className="mb-3 inline-flex size-8 items-center justify-center rounded-sm border border-border font-mono text-xs">
                {step.step}
              </div>
              <p className="font-medium">{step.name}</p>
              <p className="mt-1 text-sm text-foreground-muted">{step.desc}</p>
              <pre className="mt-4 whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-foreground-subtle">
                {step.snippet}
              </pre>
            </div>
          ))}
        </div>
      </div>
    </SectionShell>
  );
}
