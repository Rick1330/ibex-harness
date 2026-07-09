import Link from "next/link";

export function LandingCta() {
  return (
    <section className="mx-auto max-w-7xl px-5 pb-24 sm:px-8">
      <div className="max-w-2xl text-center md:mx-auto">
        <p className="mb-4 text-xs tracking-widest text-muted-foreground">
          {"// READY WHEN YOU ARE"}
        </p>
        <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
          Put agent memory at the proxy.
        </h2>
        <p className="mx-auto mt-4 max-w-md text-sm leading-relaxed text-muted-foreground">
          Read the docs, explore benchmarks, and follow the roadmap for memory
          and context assembly.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/docs/getting-started/introduction"
            className="ascii-frame bg-primary px-5 py-3 text-sm font-bold text-primary-foreground transition-transform hover:-translate-y-0.5"
          >
            Get started
          </Link>
          <Link
            href="/benchmarks"
            className="ascii-frame bg-paper px-5 py-3 text-sm font-bold transition-transform hover:-translate-y-0.5"
          >
            View benchmarks
          </Link>
        </div>
      </div>
    </section>
  );
}
