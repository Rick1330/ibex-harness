import { SectionShell } from "@/components/chrome/section-shell";
import { CodeShell } from "@/components/site/code-shell";
import { STACK_PORTS, STACK_SHELL_LINES } from "@/lib/landing-content";

/** §04 · Local Stack (DESIGN_GUIDE.md §12.5). */
export function LandingTerminal() {
  return (
    <SectionShell id="local-stack" section="§04" label="LOCAL STACK">
      <div className="grid items-start gap-12 lg:grid-cols-2 lg:gap-14">
        <div>
          <h2 className="landing-h2 max-w-[14ch]">
            Run the full stack locally.
          </h2>
          <p className="landing-body mt-5 max-w-[42ch]">
            This is the practical setup path: clone the repo, seed the dev data,
            bring up proxy plus auth, and verify the health endpoint before you
            wire an agent to it.
          </p>
          <ul className="landing-stack-ports mt-10">
            {STACK_PORTS.map((port) => (
              <li key={port.index} className="landing-stack-port">
                <span className="landing-stack-port-index" aria-hidden>
                  {port.index}
                </span>
                <span className="landing-body text-foreground">
                  {port.label}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="landing-flow-shell">
          <CodeShell
            title="docker-compose.yml"
            tag="compose"
            lines={STACK_SHELL_LINES}
            statusRight="local setup · phase 2"
            testId="stack-shell"
          />
        </div>
      </div>
    </SectionShell>
  );
}
