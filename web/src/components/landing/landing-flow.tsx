import { SectionShell } from "@/components/chrome/section-shell";
import { CodeShell } from "@/components/site/code-shell";
import {
  REQUEST_PATH_STEPS,
  REQUEST_TRACE_SHELL,
} from "@/lib/landing-content";

/** §03 · Request Path — sunken band, shell | numbered pipeline. */
export function LandingFlow() {
  return (
    <SectionShell
      id="request-path"
      section="§03"
      label="REQUEST PATH"
      className="!border-border bg-surface-sunken"
    >
      <div className="max-w-[52ch]">
        <h2 className="landing-h2 max-w-[18ch]">
          Every LLM call passes through{" "}
          <em className="italic">one gate</em>.
        </h2>
        <p className="landing-lede mt-5">
          Identity, policy, and tracing happen before the provider sees a
          token — one ingress, four decisive steps.
        </p>
      </div>

      <div className="mt-12 grid items-stretch gap-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:gap-12">
        <div className="landing-flow-shell">
          <CodeShell
            title="IBEX-PROXY — REQUEST TRACE"
            tag="live"
            lines={REQUEST_TRACE_SHELL}
            statusRight="trace_id 7f3a…c21 · 17.4ms"
            testId="request-trace-shell"
            className="h-full"
          />
        </div>

        <ol className="landing-flow-steps">
          {REQUEST_PATH_STEPS.map((step, index) => (
            <li key={step.step} className="landing-flow-step">
              <span className="landing-flow-step-chip" aria-hidden>
                {step.step}
              </span>
              <div className="min-w-0">
                <p className="landing-flow-step-title">
                  <span className="landing-flow-step-meta">
                    Step {index + 1} of {REQUEST_PATH_STEPS.length}
                  </span>
                  {step.title}
                </p>
                <p className="landing-small mt-1.5">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </SectionShell>
  );
}
