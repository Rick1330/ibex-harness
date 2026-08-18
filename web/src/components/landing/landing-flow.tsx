import {
  ArrowRight,
  BookText,
  ShieldCheck,
  Upload,
  Waypoints,
} from "lucide-react";

import { SectionShell } from "@/components/chrome/section-shell";
import { REQUEST_PATH_STEPS } from "@/lib/landing-content";

const [ingressStep, controlStep, contextStep, executionStep] =
  REQUEST_PATH_STEPS;

const FLOW_STEPS = [
  { ...ingressStep, Icon: Upload, showArrow: true },
  { ...controlStep, Icon: ShieldCheck, showArrow: true },
  { ...contextStep, Icon: BookText, showArrow: true },
  { ...executionStep, Icon: Waypoints, showArrow: false },
] as const;

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
          {FLOW_STEPS.map(({ Icon, showArrow, step, eyebrow, title, body }) => (
            <li key={step} className="landing-flow-node">
              <div className="landing-flow-card">
                <div className="landing-flow-card-top">
                  <span className="landing-flow-step-chip" aria-hidden>
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="landing-flow-card-kicker">
                    {step} · {eyebrow}
                  </span>
                </div>
                <p className="landing-flow-step-title mt-4">{title}</p>
                <p className="landing-small mt-2">{body}</p>
              </div>
              {showArrow ? (
                <div className="landing-flow-arrow" aria-hidden>
                  <ArrowRight className="h-4 w-4" />
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      </div>
    </SectionShell>
  );
}
