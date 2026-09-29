export default async function DeferredConsoleRoute({
  searchParams,
}: Readonly<{
  searchParams: Promise<{ route?: string }>
}>) {
  const { route } = await searchParams
  const routeLabel = typeof route === "string" && route.startsWith("/dashboard/") ? route : "/dashboard"
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 py-16">
      <section aria-labelledby="deferred-route-title" className="w-full max-w-lg rounded-lg border border-border/70 bg-card p-8 shadow-sm">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">IBEX Console</p>
        <h1 id="deferred-route-title" className="mt-3 text-2xl font-semibold">This Console surface is deferred</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{routeLabel} belongs to a later Phase 4 milestone. No domain fixtures or live data are served from this route.</p>
        <p className="mt-5 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 font-mono text-xs text-amber-900 dark:text-amber-200">The current D1 slice is the authenticated operational Overview.</p>
      </section>
    </main>
  )
}
