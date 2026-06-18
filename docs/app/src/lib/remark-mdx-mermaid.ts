import type { Code, Parent, Root } from "mdast";
import { visit } from "unist-util-visit";

import { hashString } from "./hash-string";
import { normalizeMermaidChart } from "./normalize-mermaid-chart";

type RemarkMdxMermaidOptions = {
  lang?: string;
};

type MdxMermaidAttribute = {
  type: "mdxJsxAttribute";
  name: string;
  value: string;
};

type MdxMermaidNode = {
  type: "mdxJsxFlowElement";
  name: "Mermaid";
  attributes: MdxMermaidAttribute[];
  children: [];
};

function buildMermaidMdxNode(diagramId: string): MdxMermaidNode {
  return {
    type: "mdxJsxFlowElement",
    name: "Mermaid",
    attributes: [{ type: "mdxJsxAttribute", name: "id", value: diagramId }],
    children: [],
  };
}

function isMermaidBlock(node: Code, expectedLang: string): boolean {
  return node.lang === expectedLang;
}

function replaceWithMermaidNode(
  parent: Parent,
  index: number,
  chart: string,
): void {
  const diagramId = `diagram-${hashString(chart)}`;
  parent.children[index] = buildMermaidMdxNode(diagramId) as (typeof parent.children)[number];
}

function transformMermaidCodeBlock(
  node: Code,
  index: number | undefined,
  parent: Parent | undefined,
  lang: string,
): void {
  if (index === undefined || !parent) return;
  if (!isMermaidBlock(node, lang)) return;

  replaceWithMermaidNode(parent, index, normalizeMermaidChart(node.value));
}

export function remarkMdxMermaid(options: RemarkMdxMermaidOptions = {}) {
  const lang = options.lang ?? "mermaid";

  return (tree: Root) => {
    visit(tree, "code", (node: Code, index, parent) => {
      transformMermaidCodeBlock(node, index, parent, lang);
    });
  };
}
