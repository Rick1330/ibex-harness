"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "fumadocs-ui/components/ui/collapsible";

import { cn } from "@/lib/cn";

type PathSyncedSidebarFolderProps = Readonly<{
  containsPath: boolean;
  headerClassName: string;
  header: ReactNode;
  children: ReactNode;
  depth: number;
}>;

export function PathSyncedSidebarFolder({
  containsPath,
  headerClassName,
  header,
  children,
  depth,
}: PathSyncedSidebarFolderProps) {
  const [open, setOpen] = useState(containsPath);

  useEffect(() => {
    setOpen(containsPath);
  }, [containsPath]);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className={headerClassName}>
        {header}
        <ChevronDown
          data-icon
          className={cn("ms-auto size-4 shrink-0 transition-transform", !open && "-rotate-90")}
        />
      </CollapsibleTrigger>
      <CollapsibleContent
        className="sidebar-folder-children"
        data-sidebar-depth={depth}
      >
        <div className="ms-3 border-s py-1.5 ps-1.5 md:ms-2">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}
