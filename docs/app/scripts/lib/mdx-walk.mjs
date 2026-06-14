import fs from "node:fs";
import path from "node:path";

/** Walk a content tree and invoke handler for each .mdx file. */
export function walkMdxFiles(root, handler) {
  function visit(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const abs = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        visit(abs);
        continue;
      }
      if (entry.name.endsWith(".mdx")) {
        handler(abs);
      }
    }
  }

  visit(root);
}

/** Read frontmatter + body from an MDX file. Returns null when malformed. */
export function readMdxParts(abs) {
  const raw = fs.readFileSync(abs, "utf8");
  const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!match) return null;
  return { fm: match[1], body: match[2] };
}

/** Write frontmatter + body back to an MDX file. */
export function writeMdxParts(abs, fm, body) {
  fs.writeFileSync(abs, `---\n${fm}\n---\n${body}`, "utf8");
}
