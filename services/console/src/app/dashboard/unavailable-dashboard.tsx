export function UnavailableDashboard() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 py-16">
      <section
        aria-labelledby="console-unavailable-title"
        className="w-full max-w-lg rounded-lg border border-border/70 bg-card p-8 shadow-sm"
      >
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          IBEX Console
        </p>
        <h1
          id="console-unavailable-title"
          className="mt-3 text-2xl font-semibold"
        >
          Overview unavailable
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          This Console build has no live operator data contract. The
          fixture-backed overview is available only in an explicitly enabled,
          non-production preview environment.
        </p>
        <p className="mt-5 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 font-mono text-xs text-amber-900 dark:text-amber-200">
          CONSOLE_DATA_MODE=preview and CONSOLE_PREVIEW=1 are required outside
          production.
        </p>
      </section>
    </main>
  )
}
