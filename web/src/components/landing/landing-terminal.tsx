import { SectionShell } from "@/components/chrome/section-shell";
import { LandingShell } from "@/components/landing/landing-shell";
import { STACK_COMMANDS, STACK_SERVICES } from "@/lib/landing-content";

export function LandingTerminal() {
  return (
    <SectionShell
      id="local-stack"
      section="§05"
      label="LOCAL STACK"
      docHref="/docs/getting-started/introduction"
    >
      <div className="grid items-start gap-10 lg:grid-cols-2">
        <div>
          <ul className="space-y-3 text-sm leading-relaxed text-foreground-muted">
            {STACK_SERVICES.map((service) => (
              <li key={service} className="flex gap-3">
                <span className="font-mono text-accent" aria-hidden>
                  ▸
                </span>
                <span>{service}</span>
              </li>
            ))}
          </ul>
        </div>
        <LandingShell compact>
          {STACK_COMMANDS.map((item) => (
            <span key={item} className="block">
              <span className="text-foreground-muted" aria-hidden>
                ~${" "}
              </span>
              {item}
            </span>
          ))}
          <span className="caret-block" aria-hidden />
        </LandingShell>
      </div>
    </SectionShell>
  );
}
