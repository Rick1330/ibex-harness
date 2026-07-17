import Link from "next/link";

import { SectionShell } from "@/components/chrome/section-shell";
import { SPEC_QUOTES } from "@/lib/landing-content";

/** §06 · From the Spec — Instrument Serif pull-quotes (design §6). */
export function LandingSpecQuotes() {
  return (
    <SectionShell
      id="from-the-spec"
      section="§06"
      label="FROM THE SPEC"
      docHref="/docs/getting-started/introduction"
    >
      <div className="space-y-10">
        {SPEC_QUOTES.map((item) => (
          <figure key={item.href} className="border-l-2 border-border pl-6">
            <blockquote className="max-w-[62ch] font-display text-2xl italic leading-snug tracking-[-0.02em]">
              “{item.quote}”
            </blockquote>
            <figcaption className="mt-4">
              <Link
                href={item.href}
                className="font-mono text-xs text-foreground-muted transition-colors hover:text-accent"
              >
                → {item.label}
              </Link>
            </figcaption>
          </figure>
        ))}
      </div>
    </SectionShell>
  );
}
