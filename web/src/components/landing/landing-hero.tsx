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
              §01 · Open source · AI agent infrastructure
            </p>
            <h1 className="landing-h1 max-w-[16ch]">
              The control plane for agents that call{" "}
              <em className="italic">LLMs</em> in production.
            </h1>
            <p className="landing-lede mt-6 max-w-[52ch]">
              Intercept every model request. Validate tenant identity. Enforce
              policy. Prepare memory context — at the proxy, not in application
              glue code.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                href="/docs/getting-started/introduction"
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
              statusRight="p99 · 18ms · trace 7f3a…c21"
              testId="hero-terminal"
              className="w-full"
            />
            <div className="landing-hero-shell-meta">
              <div className="landing-hero-shell-chip inline-flex items-center gap-2">
                <span className="landing-hero-shell-chip-dot" aria-hidden />
                <span>operational</span>
              </div>
              <div className="landing-hero-shell-chip">make up</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
