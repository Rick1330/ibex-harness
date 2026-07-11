import { Reveal } from "@/components/landing/reveal";
import { LandingShell } from "@/components/landing/landing-shell";
import { STACK_COMMANDS } from "@/lib/landing-content";

export function LandingTerminal() {
  return (
    <section id="docs" className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
      <div className="grid items-center gap-10 lg:grid-cols-2">
        <div className="max-w-md">
          <p className="mb-3 text-xs tracking-widest text-muted-foreground">
            {"// LOCAL STACK"}
          </p>
          <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            Run the harness on your machine.
          </h2>
          <p className="mt-5 text-sm leading-relaxed text-muted-foreground">
            Clone the monorepo, apply migrations, and bring up the Phase 1
            compose stack for proxy, auth, Postgres, and Redis.
          </p>
          <LandingShell compact className="mt-6">
            {STACK_COMMANDS.map((item) => (
              <span key={item} className="block">
                <span className="text-accent" aria-hidden>
                  ▸{" "}
                </span>
                {item}
              </span>
            ))}
          </LandingShell>
        </div>
        <Reveal>
          <div className="ascii-frame overflow-hidden bg-card">
            <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-destructive/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-accent/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/50" />
              <span className="ml-2 text-[11px] text-muted-foreground">
                ibex-proxy — request
              </span>
            </div>
            <pre className="overflow-x-auto p-5 text-[12px] leading-relaxed">
              {`POST /v1/chat/completions
X-IBEX-Agent-ID: <uuid>
Authorization: Bearer <token>

→ auth.ValidateAgent (gRPC)
→ ratelimit.Check (Redis)
→ forward to provider
← 200 OK · trace_id=7f3a…c21`}
              <span className="caret">▊</span>
            </pre>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
