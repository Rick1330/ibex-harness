import { statSync } from "node:fs";
import { join } from "node:path";

import { cache } from "react";
type PageWithFile = {
  file: {
    path: string;
  };
};

/** Read mtime once per page per build/request (React cache). Safe for SSG. */
export const getPageLastModified = cache(
  (page: PageWithFile, contentDir = "content/docs"): Date => {
    const relative = page.file.path.replace(/\\/g, "/");
    const absolute = join(process.cwd(), contentDir, relative);
    return statSync(absolute).mtime;
  },
);
