import { SectionShell } from "@/components/chrome/section-shell";
import {
  METRICS,
  STACK_COMMANDS,
  STACK_LOGS,
  STACK_PORTS,
} from "@/lib/landing-content";

export function LandingTerminal() {
  return (
    <SectionShell id="local-stack" section="§04" label="LOCAL STACK" hideHeader>
      <div className="py-14 sm:py-20">
        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-12">
          <div>
            <p className="mb-4 font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
              §04 · LOCAL STACK
            </p>
            <h2 className="max-w-[16ch] font-display text-[length:var(--text-4xl)] leading-[1.05] tracking-[-0.02em]">
              Run the harness on your machine.
            </h2>
            <p className="mt-5 max-w-[42ch] text-base leading-relaxed text-foreground-muted">
              Clone the monorepo, apply migrations, and bring up the Phase 1
              compose stack for proxy, auth, Postgres, and Redis.
            </p>
            <ul className="mt-8 space-y-3">
              {STACK_PORTS.map((port) => (
                <li key={port.index} className="flex items-center gap-3 font-mono text-sm">
                  <span className="text-foreground-subtle">{port.index}</span>
                  <span>{port.label}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="overflow-hidden rounded-md border border-border bg-[oklch(0.145_0.004_60)] text-[oklch(0.955_0.006_88)]">
            <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2.5">
              <span className="size-2 rounded-full bg-white/25" aria-hidden />
              <span className="size-2 rounded-full bg-white/25" aria-hidden />
              <span className="size-2 rounded-full bg-white/25" aria-hidden />
              <span className="ml-2 font-mono text-[11px] text-white/50">
                DOCKER-COMPOSE.YML
              </span>
            </div>
            <pre className="overflow-x-auto p-4 font-mono text-[12px] leading-relaxed">
              {STACK_COMMANDS.map((cmd) => (
                <span key={cmd} className="block">
                  <span className="text-white/45">$ </span>
                  {cmd}
                </span>
              ))}
              <span className="mt-4 block space-y-1 text-white/55">
                {STACK_LOGS.map((line) => (
                  <span key={line} className="block">
                    {line}
                  </span>
                ))}
              </span>
            </pre>
          </div>
        </div>

        <div className="mt-14 grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          {METRICS.map((metric) => (
            <div key={metric.label} className="bg-background px-5 py-7">
              <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-foreground-muted">
                {metric.label}
              </p>
              <p className="mt-3 font-display text-4xl tracking-[-0.02em]">
                {metric.value}
              </p>
            </div>
          ))}
        </div>
      </div>
    </SectionShell>
  );
}
