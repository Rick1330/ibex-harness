import type { InlineCode, Link, Root } from "mdast";
import { visit } from "unist-util-visit";

import { getCommitUrl } from "./github";

const SHA_RE = /^[a-f0-9]{7,40}$/i;

export function remarkGitSha() {
  return (tree: Root) => {
    visit(tree, "inlineCode", (node: InlineCode, index, parent) => {
      if (index === undefined || !parent) return;
      const value = node.value.trim();
      if (!SHA_RE.test(value)) return;

      const link: Link = {
        type: "link",
        url: getCommitUrl(value),
        children: [{ type: "text", value }],
      };
      parent.children[index] = link;
    });
  };
}
