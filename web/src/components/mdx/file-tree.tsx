"use client";

import { ChevronRight, File } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";

type FileTreeProps = Readonly<{
  children: ReactNode;
}>;

export function FileTree({ children }: FileTreeProps) {
  return (
    <div className="my-6 rounded-md border border-border bg-panel p-4 font-mono text-sm">
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

type FolderItemProps = Readonly<{
  name: string;
  children?: ReactNode;
  defaultOpen?: boolean;
}>;

export function FolderItem({
  name,
  children,
  defaultOpen = false,
}: FolderItemProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div>
      <button
        className={cn(
          "flex w-full items-center gap-2 rounded-[4px] px-2 py-1 text-left transition-colors",
          "hover:bg-panel-raised",
        )}
        onClick={() => { setOpen((value) => !value); }}
        type="button"
      >
        <ChevronRight
          className={cn(
            "size-4 shrink-0 text-text-tertiary transition-transform duration-150",
            open && "rotate-90",
          )}
          strokeWidth={1.5}
        />
        <span className="font-medium text-text-primary">{name}/</span>
      </button>
      {open && children ? (
        <div className="ms-4 mt-0.5 space-y-0.5 border-s border-border ps-2">
          {children}
        </div>
      ) : null}
    </div>
  );
}

type FileItemProps = Readonly<{
  name: string;
  highlight?: boolean;
}>;

export function FileItem({ name, highlight = false }: FileItemProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-[4px] px-2 py-1 transition-colors",
        highlight
          ? "border-s-2 border-accent bg-panel-raised font-medium text-text-primary"
          : "hover:bg-panel-raised",
      )}
    >
      <File className="size-4 shrink-0 text-text-tertiary" strokeWidth={1.5} />
      <span>{name}</span>
    </div>
  );
}
