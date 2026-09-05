"use client";

import type { ContentBaseUrl } from "@/lib/sidebar-icon-resolvers";
import type { MobileNavNode } from "@/lib/mobile-nav-data";
import { Brain, ClipboardCheck, Gauge, PenLine, Target } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, type ReactNode } from "react";

import {
  docsNestedFolderHeaderClassName,
  docsSectionHeaderClassName,
  docsSidebarItemClassName,
} from "@/components/layout/docs-sidebar";
import { PathSyncedSidebarFolder } from "@/components/layout/path-synced-sidebar-folder";
import { cn } from "@/lib/cn";
import { resolveLeafNavIcon } from "@/lib/sidebar-page-icon";
import { SidebarIcon } from "@/lib/sidebar-icons";
import { navUrlsMatch } from "@/lib/sidebar-nav-pages";

type MobilePageTreeNavProps = Readonly<{
  nodes: MobileNavNode[];
  baseUrl: ContentBaseUrl;
  level?: number;
  parentKey?: string;
  activeFolderKeys?: ReadonlySet<string>;
  onNavigate?: () => void;
}>;

function folderContainsNode(
  folder: Extract<MobileNavNode, { kind: "folder" }>,
  pathname: string,
): boolean {
  for (const child of folder.children) {
    if (child.kind === "page" && navUrlsMatch(child.url, pathname)) {
      return true;
    }
    if (child.kind === "folder" && folderContainsNode(child, pathname)) {
      return true;
    }
  }
  return false;
}

function collectActiveFolderKeys(
  nodes: MobileNavNode[],
  pathname: string,
  parentKey = "",
): Set<string> {
  const keys = new Set<string>();

  nodes.forEach((node, index) => {
    if (node.kind !== "folder") return;

    const key = parentKey ? `${parentKey}/${node.name}-${index}` : `${node.name}-${index}`;
    if (!folderContainsNode(node, pathname)) return;

    keys.add(key);
    collectActiveFolderKeys(node.children, pathname, key).forEach((childKey) => {
      keys.add(childKey);
    });
  });

  return keys;
}

function firstPageUrl(nodes: readonly MobileNavNode[]): string | undefined {
  for (const node of nodes) {
    if (node.kind === "page") {
      return node.url;
    }
    if (node.kind === "folder") {
      const nested = firstPageUrl(node.children);
      if (nested) {
        return nested;
      }
    }
  }
  return undefined;
}

function folderHeaderIcon(
  folderName: string,
  children: readonly MobileNavNode[],
  baseUrl: ContentBaseUrl,
): ReactNode {
  if (baseUrl === "/benchmarks") {
    const byName = {
      Proxy: Gauge,
      Memory: Brain,
      "Extraction quality": ClipboardCheck,
      HNSW: Brain,
      "Ranking quality": Target,
      "Write pipeline": PenLine,
    } as const;
    const Icon = byName[folderName as keyof typeof byName];
    if (Icon) {
      return <SidebarIcon className="sidebar-section-icon" icon={Icon} />;
    }
  }

  const url = firstPageUrl(children);
  return url ? resolveLeafNavIcon(url, baseUrl) : null;
}

function MobilePageTreeNav({
  nodes,
  baseUrl,
  level = 1,
  parentKey = "",
  activeFolderKeys,
  onNavigate,
}: MobilePageTreeNavProps) {
  const pathname = usePathname();
  const computedKeys = useMemo(
    () => collectActiveFolderKeys(nodes, pathname),
    [nodes, pathname],
  );
  const folderKeys = activeFolderKeys ?? computedKeys;

  return (
    <>
      {nodes.map((node, index) => {
        if (node.kind === "folder") {
          const headerClass =
            level <= 1
              ? docsSectionHeaderClassName
              : docsNestedFolderHeaderClassName;
          const folderKey = parentKey
            ? `${parentKey}/${node.name}-${index}`
            : `${node.name}-${index}`;

          return (
            <PathSyncedSidebarFolder
              key={folderKey}
              containsPath={folderKeys.has(folderKey)}
              headerClassName={headerClass}
              header={
                <>
                  {folderHeaderIcon(node.name, node.children, baseUrl)}
                  <span className="min-w-0 flex-1 text-left break-words">
                    {node.name}
                  </span>
                </>
              }
              depth={level}
            >
              <MobilePageTreeNav
                nodes={node.children}
                baseUrl={baseUrl}
                level={level + 1}
                parentKey={folderKey}
                activeFolderKeys={folderKeys}
                onNavigate={onNavigate}
              />
            </PathSyncedSidebarFolder>
          );
        }

        const isMilestone = node.url.includes("/milestones/");
        const isActive = navUrlsMatch(node.url, pathname);
        const pageKey = parentKey ? `${parentKey}/${node.url}-${index}` : `${node.url}-${index}`;

        return (
          <Link
            key={pageKey}
            href={node.url}
            prefetch
            onClick={onNavigate}
            data-active={isActive ? "true" : undefined}
            className={cn(
              docsSidebarItemClassName(
                isMilestone ? "sidebar-nav-item--milestone" : undefined,
              ),
            )}
          >
            {resolveLeafNavIcon(node.url, baseUrl)}
            <span className="min-w-0 flex-1 break-words">{node.name}</span>
          </Link>
        );
      })}
    </>
  );
}

export { MobilePageTreeNav };
