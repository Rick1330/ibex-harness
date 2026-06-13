import { defineConfig, defineDocs } from "fumadocs-mdx/config";
import { rehypeCode } from "fumadocs-core/mdx-plugins";

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

export const docs = defineDocs({
  dir: "content/docs",
});

export default defineConfig({
  mdxOptions: {
    rehypePlugins: [
      [
        rehypeCode,
        {
          themes: {
            light: "github-light-default",
            dark: "github-dark-default",
          },
          keepBackground: false,
          lazy: true,
          langs: [...DOC_LANGS],
          // Faster Shiki init on Windows (avoids loading oniguruma WASM per worker).
          experimentalJSEngine: true,
        },
      ],
    ],
  },
});
