import {
  defineConfig,
  defineCollections,
  defineDocs,
  frontmatterSchema,
} from "fumadocs-mdx/config";
import { rehypeCode, rehypeCodeDefaultOptions } from "fumadocs-core/mdx-plugins";
import { z } from "zod";

import { attachCodeLanguageTransformer } from "./src/lib/rehype-attach-code-language";
import { remarkGitSha } from "./src/lib/remark-git-sha";
import { remarkMdxMermaid } from "./src/lib/remark-mdx-mermaid";

const DOC_LANGS = [
  "bash",
  "json",
  "javascript",
  "typescript",
  "tsx",
  "python",
  "yaml",
  "mdx",
  "go",
  "dockerfile",
  "go",
  "sql",
  "xml",
  "text",
  "ini",
  "toml",
  "powershell",
  "sh",
] as const;

export const docs = defineDocs({
  dir: "content/docs",
  docs: {
    schema: frontmatterSchema.extend({
      adrId: z.string().optional(),
      status: z.string().optional(),
      date: z.string().optional(),
      authors: z.string().optional(),
    }),
  },
});

export const blog = defineCollections({
  type: "doc",
  dir: "content/blog",
  schema: frontmatterSchema.extend({
    date: z.string(),
    author: z.string().optional(),
    authorUrl: z.string().url().optional(),
    tags: z.array(z.string()).optional(),
    excerpt: z.string().optional(),
    readingTime: z.string().optional(),
    featured: z.boolean().optional(),
  }),
});

export const releases = defineCollections({
  type: "doc",
  dir: "content/releases",
  schema: frontmatterSchema.extend({
    version: z.string(),
    date: z.string(),
    type: z.enum(["major", "minor", "patch"]).default("patch"),
  }),
});

const roadmapDocSchema = frontmatterSchema.extend({
  summary: z.string().optional(),
  status: z.enum(["completed", "in-progress", "planned"]).optional(),
  milestoneId: z.string().optional(),
  goal: z.string().optional(),
  estimatedEffort: z.string().optional(),
  phase: z.string().optional(),
  completedDate: z.string().optional(),
  fullTitle: z.string().optional(),
  sidebarTitle: z.string().optional(),
});

export const roadmap = defineDocs({
  dir: "content/roadmap",
  docs: {
    schema: roadmapDocSchema,
  },
});

export default defineConfig({
  mdxOptions: {
    remarkPlugins: [remarkMdxMermaid, remarkGitSha],
    rehypePlugins: [
      [
        rehypeCode,
        {
          themes: {
            light: "light-plus",
            dark: "dark-plus",
          },
          defaultColor: false,
          keepBackground: false,
          lazy: true,
          langs: [...DOC_LANGS],
          transformers: [
            ...(rehypeCodeDefaultOptions.transformers ?? []),
            attachCodeLanguageTransformer(),
          ],
          experimentalJSEngine: true,
        },
      ],
    ],
  },
});
