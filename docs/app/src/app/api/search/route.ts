import type { NextRequest } from "next/server";

import { search } from "@/lib/search";

// Pre-build the Orama index at deploy time. Dynamic GET rebuilds the index per
// request and exceeds Cloudflare Worker CPU limits on production.
export const dynamic = "force-static";
export const revalidate = false;

const { GET: dynamicGET, staticGET } = search;

export async function GET(request: NextRequest) {
  if (process.env.NODE_ENV === "development") {
    return dynamicGET(request);
  }
  return staticGET();
}
