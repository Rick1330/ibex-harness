import type { Code, Root } from "mdast";
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

export function remarkMdxMermaid(options: RemarkMdxMermaidOptions = {}) {
  const lang = options.lang ?? "mermaid";

  return (tree: Root) => {
    visit(tree, "code", (node: Code, index, parent) => {
      if (node.lang !== lang || index === undefined || !parent) return;

      const chart = node.value.trim();
      const diagramId = `diagram-${hashString(chart)}`;
      parent.children[index] = buildMermaidMdxNode(chart, diagramId) as (typeof parent.children)[number];
    });
  };
}
