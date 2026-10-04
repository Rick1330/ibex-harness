import { statSync } from "node:fs";
import { join } from "node:path";

import { cache } from "react";

type PageWithFileInfo = {
  data: {
    info: {
      path: string;
    };
  };
};

/** Read mtime once per page per build/request (React cache). Skips on Workers (no content FS). */
export const getPageLastModified = cache(
  (page: PageWithFileInfo, contentDir = "content/docs"): Date | undefined => {
    try {
      const relative = page.data.info.path.replace(/\\/g, "/");
      const absolute = join(process.cwd(), contentDir, relative);
      return statSync(absolute).mtime;
    } catch {
      return undefined;
    }
  },
);
