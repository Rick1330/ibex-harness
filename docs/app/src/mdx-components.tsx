import defaultMdxComponents from "fumadocs-ui/mdx";
import type { MDXComponents } from "mdx/types";

import { Badge } from "@/components/mdx/badge";
import { Callout } from "@/components/mdx/callout";
import { CardGrid, DocCard } from "@/components/mdx/card-grid";
import { CodeTab, CodeTabs } from "@/components/mdx/code-tabs";
import { Diagram } from "@/components/mdx/diagram";
import { Endpoint } from "@/components/mdx/endpoint";
import { FeatureGrid } from "@/components/mdx/feature-grid";
import { FileItem, FileTree, FolderItem } from "@/components/mdx/file-tree";
import { Icon } from "@/components/mdx/icon";
import { InstallCommand } from "@/components/mdx/install-command";
import { Kbd, KbdCombo } from "@/components/mdx/kbd";
import { MermaidAscii } from "@/components/mdx/mermaid-ascii";
import { ParamTable } from "@/components/mdx/param-table";
import { Pre } from "@/components/mdx/pre";
import { ProcessSteps } from "@/components/mdx/process-steps";
import { QuickLinks } from "@/components/mdx/quick-links";
import { StatusBadge } from "@/components/mdx/status-badge";
import { Step, Steps } from "@/components/mdx/steps";
import { VersionBadge } from "@/components/mdx/version-badge";

export function getMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    pre: Pre,
    Callout,
    Steps,
    Step,
    ProcessSteps,
    FeatureGrid,
    Diagram,
    Mermaid: MermaidAscii,
    MermaidAscii,
    CodeTabs,
    CodeTab,
    Endpoint,
    Badge,
    Kbd,
    kbd: Kbd,
    KbdCombo,
    InstallCommand,
    FileTree,
    FolderItem,
    FileItem,
    CardGrid,
    DocCard,
    ParamTable,
    VersionBadge,
    QuickLinks,
    StatusBadge,
    Icon,
    ...components,
  };
}

/** MDX convention export — not a React hook; prefer getMDXComponents in Server Components. */
export function useMDXComponents(components?: MDXComponents): MDXComponents {
  return getMDXComponents(components);
}
