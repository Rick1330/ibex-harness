import { SectionShell } from "@/components/chrome/section-shell";
import { STACK_COMMANDS, STACK_SERVICES } from "@/lib/landing-content";

/** §05 · Local Stack — services + compose terminal (design §6). */
export function LandingTerminal() {
  return (
    <SectionShell
      id="local-stack"
      section="§05"
      label="LOCAL STACK"
      docHref="/docs/getting-started/introduction"
    >
      <div className="grid items-start gap-10 lg:grid-cols-2">
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

        <div className="overflow-hidden rounded-md border border-border bg-surface-2">
          <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
            <span className="size-2 rounded-full bg-foreground-subtle" aria-hidden />
            <span className="size-2 rounded-full bg-foreground-subtle" aria-hidden />
            <span className="size-2 rounded-full bg-foreground-subtle" aria-hidden />
            <span className="ml-2 font-mono text-[11px] text-foreground-muted">
              docker-compose.yml
            </span>
          </div>
          <pre className="overflow-x-auto p-4 font-mono text-[12px] leading-relaxed">
            {STACK_COMMANDS.map((cmd) => (
              <span key={cmd} className="block">
                <span className="text-foreground-muted">$ </span>
                {cmd}
              </span>
            ))}
            <span className="caret-block" aria-hidden />
          </pre>
        </div>
      </div>
    </SectionShell>
  );
}
