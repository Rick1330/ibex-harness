import { search } from "@/lib/search";

// Pre-build the Orama index at deploy time. Dynamic GET rebuilds the index per
// request and exceeds Cloudflare Worker CPU limits on production.
export const dynamic = "force-static";
export const revalidate = false;

export const { staticGET: GET } = search;
