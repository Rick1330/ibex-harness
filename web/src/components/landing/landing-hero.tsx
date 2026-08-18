import Link from "next/link";

import { CodeShell } from "@/components/site/code-shell";
import { HERO_SHELL_LINES, REPO_URL } from "@/lib/landing-content";

/**
 * §01 Hero — copy left, CodeShell right (DESIGN_GUIDE.md §12.1–12.2).
 * Shell: hidden sm, compact md, always filled lg+.
 */
export function LandingHero() {
  return (
    <section id="overview" className="border-b border-border">
      <div className="landing-hero-inner py-24 lg:py-32">
        <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.95fr)] xl:gap-20">
          <div className="min-w-0">
            <p className="landing-eyebrow mb-5">
              §01 · Open source · Agent memory infrastructure
            </p>
            <h1 className="landing-h1 max-w-[16ch]">
              Agent memory belongs{" "}
              <em className="italic">on the request path</em>.
            </h1>
            <p className="landing-lede mt-6 max-w-[48ch]">
              IBEX Harness turns the proxy into the place where identity,
              context, and eventually memory are applied. Auth, directives, and
              mock/live forwarding are live now; memory retrieval joins that same
              ingress in Phase 3.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-3">
              <Link
                href="/docs"
                className="btn-solid"
              >
                Read the docs →
              </Link>
              <a
                href={REPO_URL}
                className="btn-outline"
                rel="noopener noreferrer"
                target="_blank"
              >
                View on GitHub
              </a>
            </div>
          </div>

          <div
            className="min-w-0 max-md:hidden"
            data-hero-shell
            data-testid="hero-shell-column"
          >
            <CodeShell
              title="~/ibex — zsh"
              tag="v0.1"
              lines={HERO_SHELL_LINES}
              statusRight="teaser · one ingress"
              testId="hero-terminal"
              className="w-full"
            />
            <div className="landing-hero-shell-meta">
              <div className="landing-hero-shell-chip inline-flex items-center gap-2">
                <span className="landing-hero-shell-chip-dot" aria-hidden />
                <span>live now</span>
              </div>
              <div className="landing-hero-shell-chip">memory next</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
