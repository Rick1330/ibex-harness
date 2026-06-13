import defaultMdxComponents from "fumadocs-ui/mdx";
import type { MDXComponents } from "mdx/types";

import { Badge } from "@/components/mdx/badge";
import { Callout } from "@/components/mdx/callout";
import { CodeTab, CodeTabs } from "@/components/mdx/code-tabs";
import { Endpoint } from "@/components/mdx/endpoint";
import { Kbd } from "@/components/mdx/kbd";
import { Step, Steps } from "@/components/mdx/steps";

export function useMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    Callout,
    Steps,
    Step,
    CodeTabs,
    CodeTab,
    Endpoint,
    Badge,
    Kbd,
    kbd: Kbd,
    ...components,
  };
}
