"use client";

import { cn } from "@/lib/cn";

type ChangelogScopeFilterProps = Readonly<{
  scopes: string[];
  activeScope: string | null;
  onChange: (scope: string | null) => void;
}>;

export function ChangelogScopeFilter({
  scopes,
  activeScope,
  onChange,
}: ChangelogScopeFilterProps) {
  if (scopes.length === 0) return null;

  return (
    <div className="-mx-4 flex items-center gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0">
      <span className="shrink-0 text-xs font-semibold uppercase tracking-widest text-text-tertiary">
        Filter
      </span>
      <button
        type="button"
        onClick={() => {
          onChange(null);
        }}
        className={cn(
          "shrink-0 rounded-[4px] border px-2.5 py-1.5 font-mono text-xs transition-colors",
          activeScope === null
            ? "border-border-strong bg-panel text-text-primary"
            : "border-border bg-canvas text-text-secondary hover:bg-panel",
        )}
      >
        all
      </button>
      {scopes.map((scope) => (
        <button
          key={scope}
          type="button"
          onClick={() => {
            onChange(scope === activeScope ? null : scope);
          }}
          className={cn(
            "shrink-0 rounded-[4px] border px-2.5 py-1.5 font-mono text-xs transition-colors",
            activeScope === scope
              ? "border-border-strong bg-panel text-text-primary"
              : "border-border bg-canvas text-text-secondary hover:bg-panel",
          )}
        >
          {scope}
        </button>
      ))}
    </div>
  );
}
