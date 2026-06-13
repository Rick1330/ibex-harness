import { statSync } from "node:fs";
import { join } from "node:path";

import type { InferPageType } from "fumadocs-core/source";
import { cache } from "react";

import type { source } from "@/lib/source";

type DocsPage = InferPageType<typeof source>;

/** Read mtime once per page per build/request (React cache). Safe for SSG. */
export const getPageLastModified = cache((page: DocsPage): Date => {
  const relative = page.file.path.replace(/\\/g, "/");
  const absolute = join(process.cwd(), "content/docs", relative);
  return statSync(absolute).mtime;
});
