/** Markdown link rewriting helpers for fix-roadmap-links.mjs */

export function parseMarkdownLink(content, index) {
  if (content[index] !== "[") return undefined;

  const textEnd = content.indexOf("]", index + 1);
  if (textEnd === -1 || content[textEnd + 1] !== "(") return undefined;

  const hrefStart = textEnd + 2;
  const hrefEnd = content.indexOf(")", hrefStart);
  if (hrefEnd === -1) return undefined;

  const text = content.slice(index + 1, textEnd);
  const href = content.slice(hrefStart, hrefEnd);
  const hashIndex = href.indexOf("#");
  const pathPart = hashIndex === -1 ? href : href.slice(0, hashIndex);
  const hash = hashIndex === -1 ? "" : href.slice(hashIndex + 1);

  return { text, pathPart, hash, end: hrefEnd + 1 };
}

export function rewriteMarkdownLinks(content, rewriteLink) {
  let result = "";
  let index = 0;

  while (index < content.length) {
    const link = parseMarkdownLink(content, index);
    if (link?.pathPart.endsWith(".md")) {
      result += rewriteLink(link);
      index = link.end;
      continue;
    }

    result += content[index];
    index += 1;
  }

  return result;
}
