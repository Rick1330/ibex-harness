import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-canvas px-6 py-16 text-center">
      <p className="font-mono text-[72px] font-medium leading-none text-text-primary">
        404
      </p>
      <h1 className="text-2xl font-semibold text-text-primary">
        Page not found
      </h1>
      <p className="max-w-md text-text-secondary">
        The page you requested does not exist or may have moved.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Link
          className="inline-flex h-9 items-center rounded-[4px] border border-border bg-transparent px-4 text-sm font-medium text-text-primary transition hover:bg-panel-raised"
          href="/"
        >
          Back to home
        </Link>
        <Link
          className="inline-flex h-9 items-center rounded-[4px] border border-border bg-transparent px-4 text-sm font-medium text-text-primary transition hover:bg-panel-raised"
          href="/docs/getting-started/introduction"
        >
          Documentation home
        </Link>
      </div>
    </main>
  );
}
