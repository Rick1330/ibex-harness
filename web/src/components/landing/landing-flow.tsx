import {
  ArrowRight,
  BookText,
  ShieldCheck,
  Upload,
  Waypoints,
} from "lucide-react";

import { SectionShell } from "@/components/chrome/section-shell";
import { REQUEST_PATH_STEPS } from "@/lib/landing-content";

const FLOW_ICONS = [Upload, ShieldCheck, BookText, Waypoints] as const;

/** §03 · Request Path — visual flow instead of prose stack. */
export function LandingFlow() {
  return (
    <SectionShell
      id="request-path"
      section="§03"
      label="REQUEST PATH"
      className="!border-border bg-surface-sunken"
    >
      <div className="landing-flow-intro">
        <h2 className="landing-h2">
          How one call moves through{" "}
          <em className="italic">the system</em>.
        </h2>
        <p className="landing-lede mt-5">
          Intake, auth, context, then forward — four steps on one ingress.
        </p>
      </div>

      <div className="mt-12">
        <ol className="landing-flow-rail">
          {REQUEST_PATH_STEPS.map((step, index) => {
            const Icon = FLOW_ICONS[index];

            return (
              <li key={step.step} className="landing-flow-node">
                <div className="landing-flow-card">
                  <div className="landing-flow-card-top">
                    <span className="landing-flow-step-chip" aria-hidden>
                      <Icon className="h-4 w-4" />
                    </span>
                    <span className="landing-flow-card-kicker">
                      {step.step} · {step.eyebrow}
                    </span>
                  </div>
                  <p className="landing-flow-step-title mt-4">{step.title}</p>
                  <p className="landing-small mt-2">{step.body}</p>
                </div>
                {index < REQUEST_PATH_STEPS.length - 1 ? (
                  <div className="landing-flow-arrow" aria-hidden>
                    <ArrowRight className="h-4 w-4" />
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
      </div>
    </SectionShell>
  );
}
