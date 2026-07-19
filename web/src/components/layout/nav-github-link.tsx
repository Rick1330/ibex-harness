"use client";

import Link from "next/link";

import { GithubIcon } from "@/components/icons/github-icon";
import { cn } from "@/lib/cn";
import { GITHUB_OWNER, GITHUB_REPO } from "@/lib/github";

type NavGithubLinkProps = Readonly<{
  className?: string;
  /** When true, label shows from `sm` up; icon-only on smaller screens. */
  showLabel?: boolean;
}>;

/** GitHub CTA — one link: icon-only on mobile, labeled pill from sm up. */
export function NavGithubLink({
  className,
  showLabel = false,
}: NavGithubLinkProps) {
  return (
    <Link
      href={`https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}`}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="GitHub repository"
      data-site-nav-github=""
      className={cn(
        "site-nav-github-link inline-flex h-9 w-9 shrink-0 items-center justify-center gap-2 rounded-sm px-0",
        "bg-primary text-primary-foreground",
        "font-sans text-[0.8125rem] font-medium tracking-tight",
        "shadow-[0_1px_0_oklch(1_0_0_/_0.12)_inset,0_1px_2px_oklch(0_0_0_/_0.18)]",
        "transition-[transform,opacity] duration-[var(--dur-1)] hover:opacity-92 active:translate-y-px",
        showLabel && "sm:w-auto sm:px-4",
        className,
      )}
    >
      <GithubIcon className="size-3.5 shrink-0" strokeWidth={1.5} />
      {showLabel ? (
        <span className="site-nav-github-label hidden sm:inline">GitHub</span>
      ) : null}
    </Link>
  );
}
