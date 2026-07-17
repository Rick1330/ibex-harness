import { SectionShell } from "@/components/chrome/section-shell";
import { FLOW, TRACE_STEPS } from "@/lib/landing-content";

export function LandingFlow() {
  return (
    <SectionShell id="request-path" section="§03" label="REQUEST PATH" hideHeader>
      <div className="py-14 sm:py-20">
        <p className="mb-4 font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
          §03 · REQUEST PATH
        </p>
        <h2 className="max-w-[18ch] font-display text-[length:var(--text-4xl)] leading-[1.05] tracking-[-0.02em]">
          Every LLM call passes through one gate.
        </h2>

        <div className="mt-10 grid items-start gap-8 lg:grid-cols-2 lg:gap-12">
          <div className="overflow-hidden rounded-md border border-border bg-[var(--surface-2)] text-foreground dark:bg-[oklch(0.12_0.004_60)]">
            <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
              <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-foreground-muted">
                IBEX-PROXY · REQUEST TRACE
              </span>
              <span className="font-mono text-[11px] text-foreground-subtle">
                7f3a…c21
              </span>
            </div>
            <pre className="overflow-x-auto p-4 font-mono text-[12px] leading-relaxed">
              <span className="block text-accent">POST /v1/chat/completions</span>
              <span className="mt-3 block text-foreground-muted">
                X-IBEX-Agent-ID: &lt;uuid&gt;
              </span>
              <span className="block text-foreground-muted">
                Authorization: Bearer &lt;token&gt;
              </span>
              <span className="mt-4 block">
                {TRACE_STEPS.map((step) => (
                  <span key={step.name} className="flex justify-between gap-4">
                    <span>→ {step.name}</span>
                    <span className="text-accent">{step.ms}</span>
                  </span>
                ))}
              </span>
            </pre>
          </div>

          <ol className="space-y-6">
            {FLOW.map((step) => (
              <li key={step.step} className="flex gap-4">
                <span className="flex size-8 shrink-0 items-center justify-center border border-border font-mono text-xs">
                  {step.step}
                </span>
                <div>
                  <p className="font-medium">{step.name}</p>
                  <p className="mt-1 text-sm leading-relaxed text-foreground-muted">
                    {step.desc}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </SectionShell>
  );
}
