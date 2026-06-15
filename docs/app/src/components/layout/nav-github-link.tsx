"use client";

import { Github } from "lucide-react";
import Link from "next/link";

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
      aria-label="GitHub"
      className={cn(
        "inline-flex items-center gap-2 rounded-[4px] px-2 py-1.5 text-sm text-text-secondary transition-colors hover:bg-panel-raised hover:text-text-primary",
        className,
      )}
    >
      <Github className="size-4 shrink-0" strokeWidth={2} />
      {showLabel ? <span className="text-xs font-medium">GitHub</span> : null}
    </Link>
  );
}
