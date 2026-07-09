import type { NextRequest } from "next/server";

import { exportStaticSearchIndex, search } from "@/lib/search";

// Dynamic so build-time prerender does not cache an empty Orama export.
// Production uses /search-index.json; /api/search exists for dev + CI extract.
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  if (!request.nextUrl.searchParams.has("query")) {
    return Response.json(await exportStaticSearchIndex());
  }

  return search.GET(request);
}
