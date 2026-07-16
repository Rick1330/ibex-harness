"use client";

import Link from "next/link";

import { GithubIcon } from "@/components/icons/github-icon";

import { cn } from "@/lib/cn";
import { GITHUB_OWNER, GITHUB_REPO } from "@/lib/github";

type NavGithubLinkProps = Readonly<{
  className?: string;
  showLabel?: boolean;
}>;

export function NavGithubLink({ className, showLabel = false }: NavGithubLinkProps) {
  return (
    <Link
      href={`https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}`}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="GitHub repository"
      data-site-nav-github=""
      className={cn(
        "site-nav-github-link inline-flex h-8 shrink-0 items-center gap-2 rounded-md border border-border/80",
        "bg-muted/25 text-muted-foreground transition-colors",
        "hover:border-border hover:bg-muted/45 hover:text-foreground",
        showLabel
          ? "w-8 justify-center px-0 lg:w-auto lg:justify-start lg:px-3"
          : "w-8 justify-center px-0",
        className,
      )}
    >
      <GithubIcon className="size-4 shrink-0" strokeWidth={1.5} />
      {showLabel ? (
        <span className="hidden text-sm font-medium lg:inline">GitHub</span>
      ) : null}
    </Link>
  );
}
