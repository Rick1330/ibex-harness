import { readdirSync } from "node:fs";
import { join } from "node:path";

import { defineConfig, defineDocs } from "fumadocs-mdx/config";
import { rehypeCode } from "fumadocs-core/mdx-plugins";

import { debugLog } from "./src/lib/debug-log";

const DOC_LANGS = [
  "bash",
  "json",
  "javascript",
  "typescript",
  "tsx",
  "python",
  "yaml",
  "mdx",
] as const;

function countMdxFiles(dir: string): number {
  let count = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) count += countMdxFiles(full);
    else if (entry.name.endsWith(".mdx")) count += 1;
  }
  return count;
}

const rehypeCodeOptions = {
  themes: {
    light: "github-light-default",
    dark: "github-dark-default",
  },
  keepBackground: false,
  lazy: true,
  langs: [...DOC_LANGS],
} as const;

debugLog("A", "source.config.ts:init", "MDX config loading", {
  mdxFileCount: countMdxFiles(join(process.cwd(), "content/docs")),
  rehypeCodeLazy: rehypeCodeOptions.lazy,
  rehypeCodeLangCount: rehypeCodeOptions.langs.length,
  turbo: process.argv.includes("--turbo"),
});

export const docs = defineDocs({
  dir: "content/docs",
});

export default defineConfig({
  mdxOptions: {
    rehypePlugins: [[rehypeCode, rehypeCodeOptions]],
  },
});

debugLog("E", "source.config.ts:init", "MDX config loaded", {});
