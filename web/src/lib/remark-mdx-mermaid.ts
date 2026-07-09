import type { Code, Parent, Root } from "mdast";
import { visit } from "unist-util-visit";

import { mermaidToAscii } from "./mermaid-to-ascii";

type RemarkMdxMermaidOptions = {
  lang?: string;
};

type MdxJsxAttribute = {
  type: "mdxJsxAttribute";
  name: string;
  value: string;
};

type MdxMermaidAsciiNode = {
  type: "mdxJsxFlowElement";
  name: "MermaidAscii";
  attributes: MdxJsxAttribute[];
  children: [];
};

function buildMermaidAsciiNode(source: string, ascii: string | null): MdxMermaidAsciiNode {
  const attributes: MdxJsxAttribute[] = [
    { type: "mdxJsxAttribute", name: "source", value: source },
  ];
  if (ascii) {
    attributes.push({ type: "mdxJsxAttribute", name: "ascii", value: ascii });
  }
  return {
    type: "mdxJsxFlowElement",
    name: "MermaidAscii",
    attributes,
    children: [],
  };
}

function isMermaidBlock(node: Code, expectedLang: string): boolean {
  return node.lang === expectedLang;
}

function replaceWithAsciiNode(parent: Parent, index: number, chart: string): void {
  const { ascii, source } = mermaidToAscii(chart);
  parent.children[index] = buildMermaidAsciiNode(source, ascii) as (typeof parent.children)[number];
}

function transformMermaidCodeBlock(
  node: Code,
  index: number | undefined,
  parent: Parent | undefined,
  lang: string,
): void {
  if (index === undefined || !parent) return;
  if (!isMermaidBlock(node, lang)) return;
  replaceWithAsciiNode(parent, index, node.value);
}

export function remarkMdxMermaid(options: RemarkMdxMermaidOptions = {}) {
  const lang = options.lang ?? "mermaid";

  return (tree: Root) => {
    visit(tree, "code", (node: Code, index, parent) => {
      transformMermaidCodeBlock(node, index, parent, lang);
    });
  };
}
