import type { Code, Parent, Root } from "mdast";
import { visit } from "unist-util-visit";

import { hashString } from "./hash-string";

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

function buildMermaidMdxNode(chart: string, diagramId: string): MdxMermaidNode {
  return {
    type: "mdxJsxFlowElement",
    name: "Mermaid",
    attributes: [
      { type: "mdxJsxAttribute", name: "id", value: diagramId },
      { type: "mdxJsxAttribute", name: "chart", value: chart },
    ],
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
  parent.children[index] = buildMermaidMdxNode(chart, diagramId) as (typeof parent.children)[number];
}

function transformMermaidCodeBlock(
  node: Code,
  index: number | undefined,
  parent: Parent | undefined,
  lang: string,
): void {
  if (index === undefined || !parent) return;
  if (!isMermaidBlock(node, lang)) return;

  replaceWithMermaidNode(parent, index, node.value.trim());
}

export function remarkMdxMermaid(options: RemarkMdxMermaidOptions = {}) {
  const lang = options.lang ?? "mermaid";

  return (tree: Root) => {
    visit(tree, "code", (node: Code, index, parent) => {
      transformMermaidCodeBlock(node, index, parent, lang);
    });
  };
}
